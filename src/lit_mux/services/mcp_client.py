"""
MCP (Model Context Protocol) client service for LIT Mux.

This module provides standalone MCP integration without dependencies on lit-lib,
implementing direct MCP server connections and tool discovery.
"""

import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, AsyncIterator
import signal
import os

logger = logging.getLogger(__name__)


class MCPServerConfig:
    """MCP server configuration."""
    def __init__(self, name: str, command: str, args: List[str] = None, env: Dict[str, str] = None, timeout: int = 10):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.timeout = timeout


class MCPServerProcess:
    """Manages a single MCP server process."""
    
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.is_running = False
        
    async def start(self) -> bool:
        """Start the MCP server process."""
        try:
            # Prepare environment
            env = os.environ.copy()
            env.update(self.config.env)
            
            # Start the process
            self.process = subprocess.Popen(
                [self.config.command] + self.config.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True
            )
            
            # Give it a moment to start
            await asyncio.sleep(0.5)
            
            # Check if it's still running
            if self.process.poll() is None:
                self.is_running = True
                logger.info(f"Started MCP server: {self.config.name}")
                return True
            else:
                logger.error(f"MCP server {self.config.name} failed to start")
                return False
                
        except Exception as e:
            logger.error(f"Failed to start MCP server {self.config.name}: {e}")
            return False
    
    async def stop(self) -> None:
        """Stop the MCP server process."""
        if self.process and self.is_running:
            try:
                # Try graceful termination first
                self.process.terminate()
                
                # Wait for graceful shutdown
                try:
                    await asyncio.wait_for(
                        asyncio.create_task(self._wait_for_process()),
                        timeout=2.0  # Reduced from 5.0 seconds
                    )
                except asyncio.TimeoutError:
                    # Force kill if it doesn't shut down gracefully
                    logger.warning(f"MCP server {self.config.name} didn't terminate gracefully, force killing")
                    self.process.kill()
                    # Don't wait after kill - just mark as stopped
                
                self.is_running = False
                logger.info(f"Stopped MCP server: {self.config.name}")
                
            except Exception as e:
                logger.error(f"Error stopping MCP server {self.config.name}: {e}")
                # Force mark as stopped even if there was an error
                self.is_running = False
    
    async def _wait_for_process(self) -> None:
        """Wait for process to terminate."""
        if self.process:
            while self.process.poll() is None:
                await asyncio.sleep(0.1)
    
    async def send_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send a JSON-RPC request to the MCP server."""
        if not self.is_running or not self.process:
            logger.warning(f"Cannot send request to {self.config.name}: server not running")
            return None
        
        try:
            # Send request
            request_json = json.dumps(request) + '\n'
            logger.debug(f"📤 Sending to {self.config.name}: {request_json.strip()}")
            
            self.process.stdin.write(request_json)
            self.process.stdin.flush()
            
            # Read response, filtering notifications
            response = await asyncio.wait_for(
                self._read_response(request.get("id")),
                timeout=self.config.timeout
            )
            
            logger.debug(f"📥 Response from {self.config.name}: {response}")
            return response
            
        except asyncio.TimeoutError:
            logger.warning(f"MCP server {self.config.name} request timeout after {self.config.timeout}s")
        except Exception as e:
            logger.error(f"MCP request error for {self.config.name}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
        
        return None
    
    async def _read_response(self, request_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """Read response from MCP server, filtering out notifications."""
        if not self.process:
            return None
        
        # Read multiple lines until we get the response or timeout
        max_lines = 50  # Prevent infinite loop
        for _ in range(max_lines):
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, self.process.stdout.readline
                )
                
                if not line:
                    break
                    
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    
                    # Skip notifications
                    if data.get("method") == "notifications/message":
                        continue
                    
                    # Check if this is our response
                    if request_id is not None and data.get("id") == request_id:
                        return data
                    elif request_id is None and "result" in data:
                        return data
                        
                except json.JSONDecodeError:
                    # Skip invalid JSON lines
                    continue
                    
            except Exception as e:
                logger.error(f"Error reading line from MCP server: {e}")
                break
        
        return None


class MCPTool:
    """Represents an MCP tool."""
    
    def __init__(self, name: str, description: str = "", parameters: Optional[Dict] = None):
        self.name = name
        self.description = description
        self.parameters = parameters or {}
        self.server_name: Optional[str] = None


class MCPClient:
    """Client for managing MCP servers and tools."""
    
    def __init__(self):
        """Initialize MCP client."""
        self.servers: Dict[str, MCPServerProcess] = {}
        self.tools: Dict[str, MCPTool] = {}
        self.request_id = 0
    
    def _get_next_request_id(self) -> int:
        """Get the next request ID."""
        self.request_id += 1
        return self.request_id
        
    async def add_server(self, config: MCPServerConfig) -> bool:
        """Add and start an MCP server."""
        server = MCPServerProcess(config)
        if await server.start():
            self.servers[config.name] = server
            
            # Initialize the MCP server with proper handshake
            if await self._initialize_server(server):
                await self._discover_tools(config.name)
                return True
            else:
                # Remove server if initialization failed
                await server.stop()
                if config.name in self.servers:
                    del self.servers[config.name]
                return False
        return False
        
    async def _initialize_server(self, server: MCPServerProcess) -> bool:
        """Initialize MCP server with proper handshake."""
        try:
            logger.info(f"🔧 Initializing MCP server: {server.config.name}")
            
            # Step 1: Send initialize request
            init_request = {
                "jsonrpc": "2.0",
                "id": self._get_next_request_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "1.0.0",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "lit-mux",
                        "version": "0.1.0"
                    }
                }
            }
            
            logger.debug(f"📤 Sending initialize request to {server.config.name}")
            init_response = await server.send_request(init_request)
            
            if not init_response or "error" in init_response:
                logger.error(f"Failed to initialize {server.config.name}: {init_response}")
                return False
                
            logger.debug(f"✅ Initialize response from {server.config.name}: {init_response}")
            
            # Step 2: Send initialized notification (no response expected)
            init_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            
            logger.debug(f"📤 Sending initialized notification to {server.config.name}")
            
            # Send notification (no response expected)
            request_json = json.dumps(init_notification) + '\n'
            server.process.stdin.write(request_json)
            server.process.stdin.flush()
            
            logger.info(f"✅ Successfully initialized MCP server: {server.config.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP server {server.config.name}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    async def _discover_tools(self, server_name: str) -> None:
        """Discover available tools from an MCP server."""
        server = self.servers.get(server_name)
        if not server:
            logger.warning(f"Cannot discover tools: server {server_name} not found")
            return
        
        logger.info(f"🔍 Starting tool discovery for server: {server_name}")
        
        try:
            # Send tools/list request
            request = {
                "jsonrpc": "2.0",
                "id": self._get_next_request_id(),
                "method": "tools/list",
                "params": {}
            }
            
            logger.debug(f"📤 Sending tools/list request: {request}")
            response = await server.send_request(request)
            logger.debug(f"📥 Received response: {response}")
            
            if response and "result" in response:
                tools_data = response["result"].get("tools", [])
                logger.info(f"🔧 Found {len(tools_data)} tools from {server_name}")
                
                for tool_data in tools_data:
                    try:
                        tool = MCPTool(
                            name=tool_data.get("name", ""),
                            description=tool_data.get("description", ""),
                            parameters=tool_data.get("inputSchema", {})
                        )
                        tool.server_name = server_name
                        
                        # Store with server prefix to avoid conflicts
                        tool_key = f"{server_name}.{tool.name}"
                        self.tools[tool_key] = tool
                        logger.info(f"✅ Registered tool: {tool_key} - {tool.description}")
                        
                    except Exception as e:
                        logger.error(f"Failed to process tool {tool_data.get('name', 'unknown')}: {e}")
                
                logger.info(f"Discovered {len(tools_data)} tools from {server_name}")
            else:
                logger.warning(f"No result in response from {server_name}: {response}")
        
        except Exception as e:
            logger.error(f"Failed to discover tools from {server_name}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def shutdown(self) -> None:
        """Shutdown all MCP servers."""
        for server in self.servers.values():
            await server.stop()
        
        self.servers.clear()
        self.tools.clear()
        logger.info("Shut down all MCP servers")
        
    async def force_shutdown(self) -> None:
        """Force immediate shutdown of all MCP servers without waiting."""
        for server in self.servers.values():
            if server.process and server.is_running:
                try:
                    server.process.kill()  # Immediate kill, no graceful termination
                    server.is_running = False
                except Exception as e:
                    logger.warning(f"Error force-killing MCP server {server.config.name}: {e}")
                    server.is_running = False
        
        self.servers.clear()
        self.tools.clear()
        logger.info("Force shut down all MCP servers")
    
    def get_available_tools(self) -> List[MCPTool]:
        """Get list of all available tools."""
        return list(self.tools.values())
    
    async def execute_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool on the specified MCP server."""
        server = self.servers.get(server_name)
        if not server:
            raise ValueError(f"MCP server {server_name} not found")
        
        if not server.is_running:
            raise ValueError(f"MCP server {server_name} is not running")
        
        try:
            # Create tool call request
            request = {
                "jsonrpc": "2.0",
                "id": self._get_next_request_id(),
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            # Send request to server
            response = await server.send_request(request)
            
            if "error" in response:
                error = response["error"]
                raise Exception(f"Tool execution error: {error.get('message', 'Unknown error')}")
            
            # Return the result
            result = response.get("result", {})
            if "content" in result:
                return result["content"]
            else:
                return result
                
        except Exception as e:
            logger.error(f"Error executing tool {tool_name} on server {server_name}: {e}")
            raise
    
    def get_tools_by_server(self, server_name: str) -> List[MCPTool]:
        """Get tools from a specific server."""
        return [tool for tool in self.tools.values() if tool.server_name == server_name]
    
    async def health_check(self) -> Dict[str, Any]:
        """Get health status of all MCP servers."""
        health_info = {
            "servers": {},
            "total_tools": len(self.tools)
        }
        
        for server_name, server in self.servers.items():
            health_info["servers"][server_name] = {
                "running": server.is_running,
                "tools": len(self.get_tools_by_server(server_name))
            }
        
        return health_info
