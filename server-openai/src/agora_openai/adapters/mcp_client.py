from __future__ import annotations
from typing import Any
import logging
import httpx
import json
import uuid

log = logging.getLogger(__name__)


class MCPToolClient:
    """MCP protocol client for tool discovery and execution via streamable-http."""
    
    def __init__(self, server_urls: dict[str, str]):
        self.servers = server_urls
        self.tool_definitions: list[dict[str, Any]] = []
        self.tool_to_server: dict[str, str] = {}
    
    async def discover_tools(self) -> list[dict[str, Any]]:
        """Discover tools from MCP servers.
        
        Returns tools in OpenAI function format.
        """
        tools = []
        
        for server_name, url in self.servers.items():
            server_tools = await self._discover_from_server(server_name, url)
            tools.extend(server_tools)
        
        self.tool_definitions = tools
        log.info("Discovered %d tools from %d servers", len(tools), len(self.servers))
        return tools
    
    async def _discover_from_server(
        self,
        server_name: str,
        url: str,
    ) -> list[dict[str, Any]]:
        """Discover tools from single MCP server using streamable-http protocol."""
        try:
            # FastMCP servers use /mcp path
            mcp_url = url if url.endswith('/mcp') else f"{url}/mcp"
            log.info("Discovering tools from %s at %s", server_name, mcp_url)
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                # MCP streamable-http protocol: send initialize request
                request_id = str(uuid.uuid4())
                mcp_request = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/list",
                    "params": {}
                }
                
                response = await client.post(
                    mcp_url,
                    json=mcp_request,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                )
                response.raise_for_status()
                
                # Parse SSE response
                mcp_response = self._parse_sse_response(response.text)
                
                # Handle MCP protocol response
                if "error" in mcp_response:
                    log.error("MCP error from %s: %s", server_name, mcp_response["error"])
                    return []
                
                result = mcp_response.get("result", {})
                tools = result.get("tools", [])
                
                openai_tools = []
                for tool in tools:
                    tool_name = tool.get("name")
                    if tool_name:
                        self.tool_to_server[tool_name] = url
                    
                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.get("name", "unknown"),
                            "description": tool.get("description", ""),
                            "parameters": tool.get("inputSchema", {
                                "type": "object",
                                "properties": {},
                            }),
                        },
                    })
                
                log.info("Discovered %d tools from %s", len(openai_tools), server_name)
                return openai_tools
                
        except Exception as e:
            log.error("Failed to discover tools from %s: %s", server_name, e, exc_info=True)
            return []
    
    async def execute_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute tool via MCP streamable-http protocol.
        
        Called by OpenAI during automatic tool loop.
        """
        log.info("Executing MCP tool: %s with parameters: %s", tool_name, parameters)
        
        server_url = self.tool_to_server.get(tool_name)
        if not server_url:
            log.error("No server found for tool: %s", tool_name)
            return {"error": f"Unknown tool: {tool_name}"}
        
        try:
            # FastMCP servers use /mcp path
            mcp_url = server_url if server_url.endswith('/mcp') else f"{server_url}/mcp"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                # MCP streamable-http protocol: send tools/call request
                request_id = str(uuid.uuid4())
                mcp_request = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": parameters
                    }
                }
                
                response = await client.post(
                    mcp_url,
                    json=mcp_request,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                )
                response.raise_for_status()
                
                # Parse SSE response
                mcp_response = self._parse_sse_response(response.text)
                
                # Handle MCP protocol response
                if "error" in mcp_response:
                    error_info = mcp_response["error"]
                    log.error("MCP error executing %s: %s", tool_name, error_info)
                    return {"error": error_info.get("message", "Tool execution failed")}
                
                result = mcp_response.get("result", {})
                log.info("Tool %s executed successfully", tool_name)
                
                # Return the result from MCP protocol
                # MCP returns content array, extract the text/data
                if "content" in result:
                    content = result["content"]
                    if isinstance(content, list) and len(content) > 0:
                        first_content = content[0]
                        if isinstance(first_content, dict):
                            # If content has text, try to parse it as JSON
                            if "text" in first_content:
                                try:
                                    return json.loads(first_content["text"])
                                except json.JSONDecodeError:
                                    return {"result": first_content["text"]}
                            return first_content
                    return {"result": content}
                
                return result
                
        except httpx.HTTPStatusError as e:
            log.error("HTTP error executing tool %s: %s - %s", tool_name, e.response.status_code, e.response.text)
            return {"error": f"HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            log.error("Tool execution failed for %s: %s", tool_name, e, exc_info=True)
            return {"error": str(e)}
    
    def _parse_sse_response(self, sse_text: str) -> dict[str, Any]:
        """Parse Server-Sent Events response to extract JSON-RPC message."""
        lines = sse_text.strip().split('\n')
        for line in lines:
            if line.startswith('data: '):
                data_str = line[6:]  # Remove 'data: ' prefix
                if data_str and data_str != '[DONE]':
                    try:
                        return json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
        
        # If no valid data found, return empty response
        log.warning("No valid JSON found in SSE response")
        return {"result": {}}

