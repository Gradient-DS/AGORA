"""MCP Client Manager using langchain-mcp-adapters for native MCP integration."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

log = logging.getLogger(__name__)


class MCPClientManager:
    """Manager for MCP server connections using langchain-mcp-adapters."""

    def __init__(self, server_urls: dict[str, str]):
        """Initialize MCP client manager with server URLs.

        Args:
            server_urls: Dictionary mapping server names to base URLs
                        e.g. {"regulation": "http://localhost:5002", ...}
        """
        self.server_urls = server_urls
        self._clients: dict[str, MultiServerMCPClient] = {}
        self._tools: list[BaseTool] = []
        self._tools_by_server: dict[str, list[BaseTool]] = {}

    async def connect(self) -> None:
        """Connect to each MCP server individually and track tools by server."""
        if not self.server_urls:
            log.info("No MCP servers configured")
            return

        for server_name, base_url in self.server_urls.items():
            mcp_url = base_url if base_url.endswith("/mcp") else f"{base_url}/mcp"
            log.info(f"Configured MCP server: {server_name} at {mcp_url}")

            config = {
                server_name: {
                    "url": mcp_url,
                    "transport": "streamable_http",
                }
            }

            try:
                client = MultiServerMCPClient(config)
                tools = await client.get_tools()

                self._clients[server_name] = client
                self._tools_by_server[server_name] = tools
                self._tools.extend(tools)

                tool_names = [getattr(t, "name", str(t)) for t in tools]
                log.info(f"Server '{server_name}' has {len(tools)} tools: {tool_names}")
            except Exception as e:
                log.error(f"Failed to connect to MCP server '{server_name}': {e}")
                self._tools_by_server[server_name] = []

        log.info(f"Loaded {len(self._tools)} tools from MCP servers")

    async def disconnect(self) -> None:
        """Disconnect from all MCP servers."""
        self._clients = {}
        self._tools = []
        self._tools_by_server = {}
        log.info("Disconnected from MCP servers")

    def get_all_tools(self) -> list[BaseTool]:
        """Get all loaded MCP tools."""
        return self._tools

    def get_tools_for_server(self, server_name: str) -> list[BaseTool]:
        """Get tools for a specific server."""
        return self._tools_by_server.get(server_name, [])

    def get_tools_by_server(self) -> dict[str, list[BaseTool]]:
        """Get all tools organized by server name."""
        return self._tools_by_server


@asynccontextmanager
async def create_mcp_client_manager(server_urls: dict[str, str]):
    """Create MCP client manager as async context manager.

    Args:
        server_urls: Dictionary mapping server names to URLs

    Yields:
        Connected MCPClientManager instance
    """
    manager = MCPClientManager(server_urls)
    try:
        await manager.connect()
        yield manager
    finally:
        await manager.disconnect()
