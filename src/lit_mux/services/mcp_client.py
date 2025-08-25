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
            # Clean up any existing process first
            if self.process:
                await self.stop()
                
            # Prepare environment
            env = os.environ.copy()
            env.update(self.config.env)
            
            # Start the process with proper file descriptor management
            self.process = subprocess.Popen(
                [self.config.command] + self.config.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                # Close file descriptors on exec to prevent leaks
                close_fds=True,
                # Set process group to allow clean termination
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
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
                await self._cleanup_process()
                return False
                
        except Exception as e:
            logger.error(f"Failed to start MCP server {self.config.name}: {e}")
            await self._cleanup_process()
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
                    if hasattr(os, 'killpg') and self.process.pid:
                        try:
                            # Kill the entire process group
                            os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                        except (OSError, ProcessLookupError):
                            # Fallback to regular kill
                            self.process.kill()
                    else:
                        self.process.kill()
                
                await self._cleanup_process()
                logger.info(f"Stopped MCP server: {self.config.name}")
                
            except Exception as e:
                logger.error(f"Error stopping MCP server {self.config.name}: {e}")
                # Force cleanup even if there was an error
                await self._cleanup_process()
    
    async def _cleanup_process(self) -> None:
        """Clean up process and file descriptors."""
        if self.process:
            try:
                # Close stdin/stdout/stderr to free file descriptors
                if self.process.stdin:
                    self.process.stdin.close()
                if self.process.stdout:
                    self.process.stdout.close()
                if self.process.stderr:
                    self.process.stderr.close()
                    
                # Wait for process cleanup
                if self.process.poll() is None:
                    self.process.wait()
                    
            except Exception as e:
                logger.warning(f"Error during process cleanup for {self.config.name}: {e}")
            finally:
                self.process = None
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
        
        # Check if process is still alive
        if self.process.poll() is not None:
            logger.warning(f"Process for {self.config.name} has died, marking as stopped")
            self.is_running = False
            await self._cleanup_process()
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
            
        except (BrokenPipeError, OSError) as e:
            logger.warning(f"Broken pipe/connection to {self.config.name}: {e}")
            self.is_running = False
            await self._cleanup_process()
            return None
        except asyncio.TimeoutError:
            logger.warning(f"MCP server {self.config.name} request timeout after {self.config.timeout}s")
            return None
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
        # Statistics for monitoring
        self.stats = {
            "servers_created": 0,
            "servers_failed": 0,
            "servers_removed": 0,
            "total_requests": 0,
            "failed_requests": 0
        }
    
    def _get_next_request_id(self) -> int:
        """Get the next request ID."""
        self.request_id += 1
        return self.request_id
        
    async def add_server(self, config: MCPServerConfig) -> bool:
        """Add and start an MCP server."""
        self.stats["servers_created"] += 1
        
        # Check if server already exists
        if config.name in self.servers:
            logger.warning(f"MCP server {config.name} already exists, stopping existing one")
            await self.remove_server(config.name)
            
        server = MCPServerProcess(config)
        if await server.start():
            self.servers[config.name] = server
            
            # Initialize the MCP server with proper handshake
            if await self._initialize_server(server):
                await self._discover_tools(config.name)
                logger.info(f"Successfully added MCP server {config.name}")
                return True
            else:
                # Clean up server if initialization failed
                logger.error(f"Failed to initialize server {config.name}, cleaning up")
                self.stats["servers_failed"] += 1
                await server.stop()
                if config.name in self.servers:
                    del self.servers[config.name]
                return False
        else:
            logger.error(f"Failed to start server {config.name}")
            self.stats["servers_failed"] += 1
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
        logger.info("Shutting down all MCP servers")
        
        # Create a list of servers to shutdown to avoid modifying dict during iteration
        servers_to_shutdown = list(self.servers.items())
        
        for server_name, server in servers_to_shutdown:
            try:
                await server.stop()
            except Exception as e:
                logger.error(f"Error shutting down server {server_name}: {e}")
        
        self.servers.clear()
        self.tools.clear()
        logger.info("Shut down all MCP servers")
    
    async def remove_server(self, server_name: str) -> bool:
        """Remove a specific MCP server."""
        if server_name not in self.servers:
            logger.warning(f"Server {server_name} not found")
            return False
        
        server = self.servers[server_name]
        
        try:
            await server.stop()
            del self.servers[server_name]
            
            # Remove tools from this server
            tools_to_remove = [tool_key for tool_key, tool in self.tools.items() 
                             if tool.server_name == server_name]
            for tool_key in tools_to_remove:
                del self.tools[tool_key]
            
            self.stats["servers_removed"] += 1
            logger.info(f"Removed MCP server {server_name} and {len(tools_to_remove)} tools")
            return True
            
        except Exception as e:
            logger.error(f"Error removing server {server_name}: {e}")
            return False
        
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
            "total_tools": len(self.tools),
            "statistics": self.stats.copy()
        }
        
        for server_name, server in self.servers.items():
            # Check if process is actually running
            process_alive = server.process and server.process.poll() is None
            
            health_info["servers"][server_name] = {
                "running": server.is_running and process_alive,
                "process_alive": process_alive,
                "tools": len(self.get_tools_by_server(server_name)),
                "pid": server.process.pid if server.process else None
            }
            
            # Update server status if process died
            if server.is_running and not process_alive:
                logger.warning(f"Detected dead process for server {server_name}")
                server.is_running = False
        
        return health_info
