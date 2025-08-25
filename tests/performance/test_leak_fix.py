#!/usr/bin/env python3
"""
Test script to verify memory leak fixes in lit-mux MCP client.
"""

import asyncio
import logging
import sys
import os
import time
import psutil
from pathlib import Path

# Add src to path to import the modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

from lit_mux.services.mcp_client import MCPClient, MCPServerConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_mcp_server_lifecycle():
    """Test adding and removing MCP servers to check for leaks."""
    logger.info("Starting MCP server lifecycle test")
    
    client = MCPClient()
    
    # Get initial process info
    process = psutil.Process()
    initial_open_files = len(process.open_files())
    initial_connections = len(process.connections())
    logger.info(f"Initial state: {initial_open_files} open files, {initial_connections} connections")
    
    # Test configuration for a dummy MCP server (will fail but tests the lifecycle)
    test_configs = [
        MCPServerConfig(
            name="test_server_1",
            command="/bin/echo",
            args=["Hello MCP"],
            timeout=5
        ),
        MCPServerConfig(
            name="test_server_2", 
            command="/bin/false",  # Command that will fail
            timeout=5
        ),
        MCPServerConfig(
            name="test_server_3",
            command="/usr/bin/python3",
            args=["-c", "print('test'); import time; time.sleep(1)"],
            timeout=5
        )
    ]
    
    # Test adding servers multiple times
    for i in range(3):
        logger.info(f"=== Test cycle {i + 1} ===")
        
        for config in test_configs:
            try:
                logger.info(f"Adding server {config.name}")
                success = await client.add_server(config)
                logger.info(f"Add server {config.name}: {'SUCCESS' if success else 'FAILED'}")
                
                # Brief pause
                await asyncio.sleep(0.5)
                
                # Remove server
                logger.info(f"Removing server {config.name}")
                removed = await client.remove_server(config.name)
                logger.info(f"Remove server {config.name}: {'SUCCESS' if removed else 'FAILED'}")
                
            except Exception as e:
                logger.error(f"Error with server {config.name}: {e}")
        
        # Check resource usage after each cycle
        current_open_files = len(process.open_files())
        current_connections = len(process.connections())
        logger.info(f"After cycle {i + 1}: {current_open_files} open files, {current_connections} connections")
        
        await asyncio.sleep(1)
    
    # Final cleanup
    logger.info("Shutting down all servers")
    await client.shutdown()
    
    # Final resource check
    final_open_files = len(process.open_files())
    final_connections = len(process.connections())
    
    logger.info(f"Final state: {final_open_files} open files, {final_connections} connections")
    logger.info(f"File descriptor change: {final_open_files - initial_open_files}")
    logger.info(f"Connection change: {final_connections - initial_connections}")
    
    # Check for leaks
    if final_open_files > initial_open_files + 5:  # Allow some margin
        logger.warning(f"Potential file descriptor leak detected: {final_open_files - initial_open_files} extra files")
        return False
    else:
        logger.info("No significant file descriptor leak detected")
        return True


async def test_server_failure_handling():
    """Test how well the system handles server failures."""
    logger.info("Testing server failure handling")
    
    client = MCPClient()
    
    # Config for a server that will start but then die
    dying_server_config = MCPServerConfig(
        name="dying_server",
        command="/usr/bin/python3",
        args=["-c", "import time; time.sleep(0.5); exit(1)"],  # Dies after 0.5s
        timeout=10
    )
    
    # Add the server
    logger.info("Adding dying server")
    success = await client.add_server(dying_server_config)
    logger.info(f"Server added: {success}")
    
    # Wait for it to die
    await asyncio.sleep(1)
    
    # Try to use it (should detect it's dead)
    logger.info("Testing dead server detection")
    health = await client.health_check()
    logger.info(f"Health check result: {health}")
    
    # Clean up
    await client.shutdown()
    logger.info("Cleanup completed")


if __name__ == "__main__":
    async def main():
        logger.info("Starting memory leak tests")
        
        # Test 1: Server lifecycle
        lifecycle_ok = await test_mcp_server_lifecycle()
        
        # Test 2: Server failure handling  
        await test_server_failure_handling()
        
        if lifecycle_ok:
            logger.info("✅ Memory leak tests PASSED")
            sys.exit(0)
        else:
            logger.error("❌ Memory leak tests FAILED")
            sys.exit(1)
    
    asyncio.run(main())
