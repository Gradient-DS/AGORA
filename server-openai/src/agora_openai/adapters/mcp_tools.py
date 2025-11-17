from __future__ import annotations
import logging
from datetime import timedelta
from typing import Callable, Awaitable, Any
from agents.mcp import MCPServer

log = logging.getLogger(__name__)


class MCPToolRegistry:
    """Registry for OpenAI Agents SDK native MCP server integration."""
    
    def __init__(self, server_urls: dict[str, str]):
        self.server_urls = server_urls
        self.mcp_servers: list[MCPServer] = []
        self._connected = False
        self.conversation_history_provider: Callable[[str], Awaitable[list[dict[str, Any]]]] | None = None
    
    def set_conversation_history_provider(
        self, 
        provider: Callable[[str], Awaitable[list[dict[str, Any]]]]
    ) -> None:
        """Set a callback to retrieve conversation history for a session.
        
        Args:
            provider: Async function that takes session_id and returns conversation history
        """
        self.conversation_history_provider = provider
        log.info("Conversation history provider registered")
    
    async def discover_and_register_tools(self) -> list[MCPServer]:
        """Create and connect native MCP server connections for Agent SDK.
        
        The Agent SDK handles MCP tool discovery and execution automatically
        when you pass MCPServer objects to the Agent constructor.
        This works for both text and voice modes.
        
        For FastMCP servers using streamable-http transport, we use MCPServerStreamableHttp.
        """
        from agents.mcp import MCPServerStreamableHttp
        
        for server_name, url in self.server_urls.items():
            # FastMCP servers with streamable-http transport expose MCP at /mcp
            mcp_url = url if url.endswith('/mcp') else f"{url}/mcp"
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
        
        log.info(f"Registered {len(self.mcp_servers)} MCP servers with Agent SDK")
        
        # Connect all servers
        await self.connect_all()
        
        return self.mcp_servers
    
    async def connect_all(self) -> None:
        """Connect all MCP servers."""
        if self._connected:
            log.debug("MCP servers already connected")
            return
        
        log.info(f"Connecting {len(self.mcp_servers)} MCP servers...")
        for mcp_server in self.mcp_servers:
            try:
                await mcp_server.connect()
                log.info(f"Connected MCP server: {mcp_server.name}")
                
                # Debug: Print tool names to identify the 65-char one
                if hasattr(mcp_server, '_tools'):
                    log.info(f"  Tools from '{mcp_server.name}':")
                    for tool in mcp_server._tools:
                        tool_name = tool.get('name') if isinstance(tool, dict) else getattr(tool, 'name', 'unknown')
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

