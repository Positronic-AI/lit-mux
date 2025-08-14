"""
MCP (Model Context Protocol) integration for LIT Mux.

This module provides the main MCP client interface used by the rest of the application.
It imports from the full mcp_client implementation.
"""

from .mcp_client import MCPClient, MCPTool, MCPServerConfig

__all__ = ["MCPClient", "MCPTool", "MCPServerConfig"]
