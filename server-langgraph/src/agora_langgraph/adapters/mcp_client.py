"""MCP Client Manager using langchain-mcp-adapters for native MCP integration."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

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
        self._client: MultiServerMCPClient | None = None
        self._tools: list[BaseTool] = []
        self._tools_by_server: dict[str, list[BaseTool]] = {}

    def _build_server_config(self) -> dict[str, dict[str, Any]]:
        """Build MultiServerMCPClient configuration from server URLs."""
        config = {}
        for server_name, base_url in self.server_urls.items():
            mcp_url = base_url if base_url.endswith("/mcp") else f"{base_url}/mcp"
            config[server_name] = {
                "url": mcp_url,
                "transport": "streamable_http",
            }
            log.info(f"Configured MCP server: {server_name} at {mcp_url}")
        return config

    async def connect(self) -> None:
        """Connect to all MCP servers and load tools."""
        if not self.server_urls:
            log.info("No MCP servers configured")
            return

        server_config = self._build_server_config()
        self._client = MultiServerMCPClient(server_config)

        self._tools = await self._client.get_tools()
        log.info(f"Loaded {len(self._tools)} tools from MCP servers")

        self._organize_tools_by_server()

    def _organize_tools_by_server(self) -> None:
        """Organize loaded tools by their source server."""
        for server_name in self.server_urls:
            self._tools_by_server[server_name] = []

        for tool in self._tools:
            tool_name = getattr(tool, "name", str(tool))
            for server_name in self.server_urls:
                if (
                    tool_name.startswith(f"{server_name}_")
                    or server_name in tool_name.lower()
                ):
                    self._tools_by_server[server_name].append(tool)
                    log.debug(f"Tool '{tool_name}' assigned to server '{server_name}'")
                    break
            else:
                if self.server_urls:
                    first_server = next(iter(self.server_urls))
                    self._tools_by_server[first_server].append(tool)
                    log.debug(
                        f"Tool '{tool_name}' assigned to default server '{first_server}'"
                    )

        for server_name, tools in self._tools_by_server.items():
            log.info(f"Server '{server_name}' has {len(tools)} tools")

    async def disconnect(self) -> None:
        """Disconnect from all MCP servers."""
        if self._client:
            self._client = None
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
