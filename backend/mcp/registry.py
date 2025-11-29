"""MCP server registry for discovering and managing MCP servers."""

import os
import json
import asyncio
from typing import Dict, Any, List, Optional
from pathlib import Path
from .client import MCPClient, MCPTool


class MCPRegistry:
    """Registry for managing MCP servers and their tools."""
    
    DEFAULT_BASE_PORT = 15000
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._find_config()
        self.clients: Dict[str, MCPClient] = {}
        self.all_tools: Dict[str, MCPTool] = {}  # Full name -> tool
        self.server_ports: Dict[str, int] = {}  # Server name -> port
        self._initialized = False
        self._base_port = self.DEFAULT_BASE_PORT
        # Status tracking
        self.server_status: Dict[str, str] = {}  # Server name -> "available" | "busy" | "offline"
        self.tools_in_use: Dict[str, bool] = {}  # Full tool name -> in_use
    
    def _find_config(self) -> str:
        """Find the mcp_servers.json config file."""
        # Look in project root
        project_root = Path(__file__).parent.parent.parent
        return str(project_root / "mcp_servers.json")
    
    def _assign_port(self, server_config: Dict[str, Any], index: int) -> Optional[int]:
        """Assign a port to a server based on config or auto-assignment."""
        # Check if server has explicit port
        explicit_port = server_config.get("port")
        if explicit_port is not None and explicit_port != "auto":
            return explicit_port
        
        # Auto-assign: base_port + index
        return self._base_port + index
    
    async def initialize(self) -> Dict[str, Any]:
        """Initialize all configured MCP servers and discover their tools."""
        if self._initialized:
            return self._get_status()
        
        # Load config
        if not os.path.exists(self.config_path):
            print(f"[MCP Registry] No config found at {self.config_path}, MCP disabled")
            self._initialized = True
            return {"enabled": False, "servers": [], "tools": []}
        
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
        except Exception as e:
            print(f"[MCP Registry] Failed to load config: {e}")
            self._initialized = True
            return {"enabled": False, "error": str(e)}
        
        # Get base port from config
        self._base_port = config.get("base_port", self.DEFAULT_BASE_PORT)
        
        servers = config.get("servers", [])
        if not servers:
            print("[MCP Registry] No servers configured")
            self._initialized = True
            return {"enabled": False, "servers": [], "tools": []}
        
        # Start each server
        project_root = Path(__file__).parent.parent.parent
        
        for index, server_config in enumerate(servers):
            name = server_config["name"]
            command = server_config.get("command", [])
            
            # Resolve command relative to project root
            if command and command[0] == "python":
                command[0] = "python3"
            
            # Determine transport mode: 
            # - "external" = connect to existing server at URL (no subprocess)
            # - "stdio" = no port, use stdin/stdout
            # - "http" = assign port (default for local servers)
            transport = server_config.get("transport", "http")
            external_url = server_config.get("url")  # For external servers
            
            if transport == "external" or external_url:
                # External server already running - just connect
                port = None
                external_url = external_url or server_config.get("url")
            elif transport == "stdio":
                # External MCP server using stdio transport (e.g., npx servers)
                port = None
                external_url = None
            else:
                # HTTP transport - assign port
                port = self._assign_port(server_config, index)
                external_url = None
            
            client = MCPClient(
                server_name=name,
                command=command,
                cwd=str(project_root),
                port=port,
                external_url=external_url
            )
            
            try:
                success = await client.start()
                if success:
                    self.clients[name] = client
                    self.server_ports[name] = port
                    self.server_status[name] = "available"  # Track status
                    # Add tools with full names
                    for tool_name, tool in client.tools.items():
                        full_name = f"{name}.{tool_name}"
                        self.all_tools[full_name] = tool
                        self.tools_in_use[full_name] = False  # Track tool usage
                    print(f"[MCP Registry] Started server: {name} on port {port}")
                else:
                    print(f"[MCP Registry] Failed to start server: {name}")
            except Exception as e:
                print(f"[MCP Registry] Error starting {name}: {e}")
        
        self._initialized = True
        return self._get_status()
    
    async def shutdown(self):
        """Shutdown all MCP servers."""
        for name, client in self.clients.items():
            try:
                await client.stop()
                print(f"[MCP Registry] Stopped server: {name}")
            except Exception as e:
                print(f"[MCP Registry] Error stopping {name}: {e}")
        
        self.clients.clear()
        self.all_tools.clear()
        self.server_ports.clear()
        self.server_status.clear()
        self.tools_in_use.clear()
        self._initialized = False
    
    def _get_status(self) -> Dict[str, Any]:
        """Get current registry status."""
        # Build server details with status
        server_details = []
        for name in self.clients.keys():
            server_tools = [
                full_name for full_name, tool in self.all_tools.items()
                if tool.server_name == name
            ]
            busy_tools = sum(1 for t in server_tools if self.tools_in_use.get(t, False))
            server_details.append({
                "name": name,
                "port": self.server_ports.get(name),
                "status": self.server_status.get(name, "offline"),
                "tool_count": len(server_tools),
                "busy_tools": busy_tools
            })
        
        return {
            "enabled": len(self.clients) > 0,
            "servers": list(self.clients.keys()),
            "server_details": server_details,
            "server_ports": self.server_ports,
            "base_port": self._base_port,
            "tools": list(self.all_tools.keys()),
            "tools_in_use": {k: v for k, v in self.tools_in_use.items() if v},  # Only active
            "tool_details": [
                {
                    "name": full_name,
                    "description": tool.description,
                    "server": tool.server_name,
                    "port": self.server_ports.get(tool.server_name),
                    "in_use": self.tools_in_use.get(full_name, False)
                }
                for full_name, tool in self.all_tools.items()
            ]
        }
    
    def get_all_tools_for_llm(self) -> List[Dict[str, Any]]:
        """Get all tool definitions in OpenAI function calling format."""
        tools = []
        for client in self.clients.values():
            tools.extend(client.get_tools_for_llm())
        return tools
    
    def get_tool_descriptions(self) -> str:
        """Get human-readable tool descriptions for prompts."""
        if not self.all_tools:
            return ""
        
        lines = ["Available tools:"]
        for full_name, tool in self.all_tools.items():
            schema = tool.input_schema
            params = schema.get("properties", {})
            param_str = ", ".join([
                f"{name}: {info.get('type', 'any')}"
                for name, info in params.items()
            ])
            lines.append(f"  - {full_name}({param_str}): {tool.description}")
        
        return "\n".join(lines)
    
    def get_detailed_tool_info(self) -> str:
        """
        Get comprehensive tool information for intelligent analysis.
        
        Returns detailed info about each MCP server and its tools including:
        - Server name and general purpose
        - Tool names, descriptions, and parameters
        - Parameter types, descriptions, and allowed values
        """
        if not self.clients:
            return ""
        
        lines = ["# Available MCP Servers and Tools\n"]
        
        for server_name, client in self.clients.items():
            port = self.server_ports.get(server_name)
            
            # Server header
            lines.append(f"## Server: {server_name}")
            lines.append(f"   Port: {port}")
            lines.append(f"   Tools:")
            
            for tool_name, tool in client.tools.items():
                full_name = f"{server_name}.{tool_name}"
                lines.append(f"\n   ### {full_name}")
                lines.append(f"       Description: {tool.description}")
                
                # Parameter details
                schema = tool.input_schema
                properties = schema.get("properties", {})
                required = schema.get("required", [])
                
                if properties:
                    lines.append("       Parameters:")
                    for param_name, param_info in properties.items():
                        param_type = param_info.get("type", "any")
                        param_desc = param_info.get("description", "")
                        is_required = param_name in required
                        req_str = "(required)" if is_required else "(optional)"
                        
                        lines.append(f"         - {param_name}: {param_type} {req_str}")
                        if param_desc:
                            lines.append(f"           Description: {param_desc}")
                        
                        # Allowed values (enum)
                        if "enum" in param_info:
                            lines.append(f"           Allowed values: {param_info['enum']}")
                        
                        # Default value
                        if "default" in param_info:
                            lines.append(f"           Default: {param_info['default']}")
                else:
                    lines.append("       Parameters: None")
            
            lines.append("")
        
        return "\n".join(lines)
    
    async def call_tool(self, full_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool by its full name (server.tool)."""
        import time
        
        if full_name not in self.all_tools:
            return {"error": f"Unknown tool: {full_name}"}
        
        tool = self.all_tools[full_name]
        client = self.clients.get(tool.server_name)
        
        if not client:
            return {"error": f"Server not running: {tool.server_name}"}
        
        # Mark tool and server as busy
        self.tools_in_use[full_name] = True
        self.server_status[tool.server_name] = "busy"
        
        start_time = time.time()
        try:
            result = await client.call_tool(tool.name, arguments)
            execution_time = round(time.time() - start_time, 3)
            return {
                "success": True,
                "server": tool.server_name,
                "tool": tool.name,
                "input": arguments,
                "output": result,
                "execution_time_seconds": execution_time
            }
        except Exception as e:
            execution_time = round(time.time() - start_time, 3)
            return {
                "success": False,
                "server": tool.server_name,
                "tool": tool.name,
                "input": arguments,
                "error": str(e),
                "execution_time_seconds": execution_time
            }
        finally:
            # Mark tool as no longer in use
            self.tools_in_use[full_name] = False
            # Check if any other tools on this server are busy
            server_tools = [
                fname for fname, t in self.all_tools.items()
                if t.server_name == tool.server_name
            ]
            any_busy = any(self.tools_in_use.get(t, False) for t in server_tools)
            self.server_status[tool.server_name] = "busy" if any_busy else "available"
    
    def should_use_tools(self, query: str) -> bool:
        """
        Determine if tool checking should be performed.
        
        With intelligent two-phase analysis, we always check with the LLM
        when tools are available. The LLM determines if tools are actually needed.
        """
        return len(self.all_tools) > 0


# Singleton instance
_registry: Optional[MCPRegistry] = None


def get_mcp_registry() -> MCPRegistry:
    """Get the global MCP registry instance."""
    global _registry
    if _registry is None:
        _registry = MCPRegistry()
    return _registry


async def initialize_mcp() -> Dict[str, Any]:
    """Initialize the global MCP registry."""
    registry = get_mcp_registry()
    return await registry.initialize()


async def shutdown_mcp():
    """Shutdown the global MCP registry."""
    global _registry
    if _registry:
        await _registry.shutdown()
        _registry = None
