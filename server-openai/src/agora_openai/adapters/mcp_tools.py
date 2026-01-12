from __future__ import annotations
import json
import logging
from datetime import timedelta
from typing import Callable, Awaitable, Any
from agents import FunctionTool
from agents.tool import ToolContext
from agents.mcp import MCPServer, MCPServerStreamableHttp

log = logging.getLogger(__name__)


def create_mcp_function_tool(
    mcp_server: MCPServerStreamableHttp,
    tool_name: str,
    tool_description: str,
    input_schema: dict[str, Any],
) -> FunctionTool:
    """Create a FunctionTool wrapper for an MCP tool.

    This wraps an MCP tool as a native SDK FunctionTool, ensuring reliable
    tool availability after agent handoffs (workaround for SDK issue #617).
    """

    async def invoke_mcp_tool(ctx: ToolContext[Any], args: str) -> str:
        """Invoke the MCP tool via the server."""
        try:
            parsed_args = json.loads(args) if args else {}
        except json.JSONDecodeError:
            parsed_args = {}

        log.info(f"🔧 FunctionTool invoking MCP: {tool_name} on {mcp_server.name}")
        log.debug(f"   Args: {parsed_args}")

        try:
            result = await mcp_server.call_tool(tool_name, parsed_args)
            # Result is typically a list of content blocks
            if isinstance(result, list):
                # Extract text from content blocks
                texts = []
                for item in result:
                    if hasattr(item, "text"):
                        texts.append(item.text)
                    elif isinstance(item, dict) and "text" in item:
                        texts.append(item["text"])
                    else:
                        texts.append(str(item))
                return "\n".join(texts)
            return str(result)
        except Exception as e:
            log.error(f"MCP tool call failed: {tool_name} - {e}")
            return json.dumps({"error": str(e)})

    # Clean up schema for OpenAI compatibility
    params_schema = input_schema.copy() if input_schema else {"type": "object", "properties": {}}
    # Remove fields that OpenAI doesn't accept
    params_schema.pop("additionalProperties", None)

    return FunctionTool(
        name=tool_name,
        description=tool_description or f"Tool: {tool_name}",
        params_json_schema=params_schema,
        on_invoke_tool=invoke_mcp_tool,
        strict_json_schema=False,  # MCP schemas may not be strict-compliant
    )


class MCPToolRegistry:
    """Registry for OpenAI Agents SDK native MCP server integration."""

    def __init__(self, server_urls: dict[str, str]):
        self.server_urls = server_urls
        self.mcp_servers: list[MCPServer] = []
        self._connected = False
        self.conversation_history_provider: (
            Callable[[str], Awaitable[list[dict[str, Any]]]] | None
        ) = None

    def set_conversation_history_provider(
        self, provider: Callable[[str], Awaitable[list[dict[str, Any]]]]
    ) -> None:
        """Set a callback to retrieve conversation history for a session.

        Args:
            provider: Async function that takes session_id and returns conversation history
        """
        self.conversation_history_provider = provider
        log.info("Conversation history provider registered")

    async def discover_and_register_tools(self) -> list[MCPServer]:
        """Create and connect native MCP server connections for Agent SDK."""
        for server_name, url in self.server_urls.items():
            self._register_single_server(server_name, url)

        log.info(f"Registered {len(self.mcp_servers)} MCP servers with Agent SDK")

        # Connect all servers
        await self.connect_all()

        return self.mcp_servers

    def _register_single_server(self, server_name: str, url: str) -> None:
        """Register a single MCP server."""
        # FastMCP servers with streamable-http transport expose MCP at /mcp
        mcp_url = url if url.endswith("/mcp") else f"{url}/mcp"
        log.info(f"Registering MCP server: {server_name} at {mcp_url}")

        # Use server_name directly - keep names short (max 64 chars for tool names)
        # The SDK prefixes tool names with this server name
        # Set timeouts for tools that make API calls (reporting extraction can take ~60s)
        # - timeout: HTTP connection timeout
        # - sse_read_timeout: SSE read timeout for HTTP streaming
        # - client_session_timeout_seconds: MCP client session request timeout (this is what was failing at 5s)
        # NOTE: Using timedelta objects for params due to SDK bug with numeric timeout parameters
        # See: https://github.com/openai/openai-agents-python/issues/845
        mcp_server = MCPServerStreamableHttp(
            name=server_name,
            params={
                "url": mcp_url,
                "timeout": timedelta(seconds=30),  # HTTP connection timeout
                "sse_read_timeout": timedelta(seconds=120),  # SSE read timeout
            },
            client_session_timeout_seconds=120,  # MCP session-level timeout (was defaulting to 5s)
        )

        self.mcp_servers.append(mcp_server)

    async def connect_all(self) -> None:
        """Connect all MCP servers and fetch their tool lists."""
        if self._connected:
            log.debug("MCP servers already connected")
            return

        log.info(f"Connecting {len(self.mcp_servers)} MCP servers...")
        for mcp_server in self.mcp_servers:
            try:
                await mcp_server.connect()
                log.info(f"Connected MCP server: {mcp_server.name}")

                # Fetch tools to populate the _tools_list cache
                # This must be called after connect() for tools to be available
                tools = await mcp_server.list_tools()
                log.info(f"  Discovered {len(tools)} tools from '{mcp_server.name}':")
                for tool in tools:
                    tool_name = getattr(tool, "name", "unknown")
                    log.info(f"    - {tool_name} ({len(tool_name)} chars)")
            except Exception as e:
                log.error(f"Failed to connect MCP server {mcp_server.name}: {e}")
                raise

        self._connected = True
        log.info("All MCP servers connected successfully")

    async def disconnect_all(self) -> None:
        """Disconnect all MCP servers."""
        if not self._connected:
            return

        log.info(f"Disconnecting {len(self.mcp_servers)} MCP servers...")
        for mcp_server in self.mcp_servers:
            try:
                await mcp_server.disconnect()
                log.info(f"Disconnected MCP server: {mcp_server.name}")
            except Exception as e:
                log.warning(f"Error disconnecting MCP server {mcp_server.name}: {e}")

        self._connected = False
        log.info("All MCP servers disconnected")

    def get_tools_by_server(self) -> dict[str, list[Any]]:
        """Get discovered tools organized by MCP server name.

        Must be called after connect_all() completes (which calls list_tools()).

        Returns:
            Dict mapping server name to list of tool definitions
        """
        if not self._connected:
            log.warning("get_tools_by_server called before servers connected")
            return {}

        tools_by_server: dict[str, list[Any]] = {}

        for mcp_server in self.mcp_servers:
            server_name = mcp_server.name
            tools_by_server[server_name] = []

            # Access the _tools_list cache populated by list_tools() in connect_all()
            if hasattr(mcp_server, "_tools_list") and mcp_server._tools_list:
                for tool in mcp_server._tools_list:
                    tools_by_server[server_name].append(tool)
                    tool_name = getattr(tool, "name", "unknown")
                    log.debug(f"Extracted tool '{tool_name}' from server '{server_name}'")
            else:
                log.warning(f"No tools found for MCP server: {server_name}")

        log.info(
            f"Extracted tools from {len(tools_by_server)} servers: "
            f"{list(tools_by_server.keys())}"
        )
        for server_name, tools in tools_by_server.items():
            log.info(f"  - {server_name}: {len(tools)} tools")

        return tools_by_server

    def get_function_tools_by_server(self) -> dict[str, list[FunctionTool]]:
        """Get FunctionTool wrappers for MCP tools, organized by server name.

        This creates native SDK FunctionTool objects that wrap MCP tools,
        ensuring reliable tool availability after agent handoffs.
        Workaround for OpenAI Agents SDK issue #617.

        Must be called after connect_all() completes.

        Returns:
            Dict mapping server name to list of FunctionTool objects
        """
        if not self._connected:
            log.warning("get_function_tools_by_server called before servers connected")
            return {}

        function_tools_by_server: dict[str, list[FunctionTool]] = {}

        for mcp_server in self.mcp_servers:
            server_name = mcp_server.name
            function_tools_by_server[server_name] = []

            if hasattr(mcp_server, "_tools_list") and mcp_server._tools_list:
                for mcp_tool in mcp_server._tools_list:
                    tool_name = getattr(mcp_tool, "name", "unknown")
                    tool_desc = getattr(mcp_tool, "description", "")
                    input_schema = getattr(mcp_tool, "inputSchema", {})

                    function_tool = create_mcp_function_tool(
                        mcp_server=mcp_server,
                        tool_name=tool_name,
                        tool_description=tool_desc,
                        input_schema=input_schema,
                    )
                    function_tools_by_server[server_name].append(function_tool)
                    log.debug(f"Created FunctionTool wrapper for '{tool_name}'")
            else:
                log.warning(f"No tools to wrap for MCP server: {server_name}")

        log.info(
            f"Created FunctionTool wrappers from {len(function_tools_by_server)} servers"
        )
        for server_name, tools in function_tools_by_server.items():
            tool_names = [t.name for t in tools[:5]]
            suffix = "..." if len(tools) > 5 else ""
            log.info(f"  - {server_name}: {len(tools)} tools ({tool_names}{suffix})")

        return function_tools_by_server
