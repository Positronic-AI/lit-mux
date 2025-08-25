#!/usr/bin/env python3
"""
Simple test script to verify memory leak fixes in lit-mux MCP client.
This version imports only the MCP client directly without FastAPI dependencies.
"""

import asyncio
import logging
import sys
import os
import time
from pathlib import Path

# Add src to path to import the modules directly
sys.path.insert(0, str(Path(__file__).parent / "src" / "lit_mux" / "services"))

# Direct import to avoid FastAPI dependencies
try:
    import mcp_client
    MCPClient = mcp_client.MCPClient
    MCPServerConfig = mcp_client.MCPServerConfig
except ImportError as e:
    logger.error(f"Failed to import MCP client: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def count_open_files():
    """Count open file descriptors for current process."""
    try:
        import subprocess
        result = subprocess.run(['lsof', '-p', str(os.getpid())], 
                              capture_output=True, text=True)
        return len(result.stdout.strip().split('\n')) - 1  # -1 for header
    except:
        # Fallback method
        try:
            fd_dir = f'/proc/{os.getpid()}/fd'
            return len(os.listdir(fd_dir))
        except:
            return -1


async def test_mcp_server_lifecycle():
    """Test adding and removing MCP servers to check for leaks."""
    logger.info("Starting MCP server lifecycle test")
    
    client = MCPClient()
    
    # Get initial file descriptor count
    initial_fds = count_open_files()
    logger.info(f"Initial file descriptors: {initial_fds}")
    
    # Test configuration for servers
    test_configs = [
        MCPServerConfig(
            name="test_echo",
            command="/bin/echo", 
            args=["test"],
            timeout=2
        ),
        MCPServerConfig(
            name="test_fail",
            command="/bin/false",  # Will fail immediately
            timeout=2
        ),
        MCPServerConfig(
            name="test_python",
            command="/usr/bin/python3",
            args=["-c", "import sys; print('Hello from Python'); sys.exit(0)"],
            timeout=2
        )
    ]
    
    # Test multiple cycles
    for cycle in range(5):
        logger.info(f"=== Cycle {cycle + 1}/5 ===")
        
        for config in test_configs:
            # Add server
            logger.info(f"Adding server: {config.name}")
            success = await client.add_server(config)
            logger.info(f"Server {config.name}: {'ADDED' if success else 'FAILED'}")
            
            # Brief wait
            await asyncio.sleep(0.2)
            
            # Check health
            health = await client.health_check()
            server_info = health.get("servers", {}).get(config.name, {})
            logger.info(f"Server {config.name} status: {server_info}")
            
            # Remove server
            logger.info(f"Removing server: {config.name}")
            removed = await client.remove_server(config.name)
            logger.info(f"Server {config.name}: {'REMOVED' if removed else 'REMOVE_FAILED'}")
        
        # Check file descriptors after each cycle
        current_fds = count_open_files()
        logger.info(f"File descriptors after cycle {cycle + 1}: {current_fds} (diff: {current_fds - initial_fds})")
        
        await asyncio.sleep(0.5)
    
    # Final cleanup
    logger.info("Final cleanup...")
    await client.shutdown()
    
    # Wait a bit for cleanup to complete
    await asyncio.sleep(1)
    
    # Final check
    final_fds = count_open_files()
    fd_diff = final_fds - initial_fds
    
    logger.info(f"Final file descriptors: {final_fds} (diff from start: {fd_diff})")
    
    # Get final statistics
    health = await client.health_check()
    stats = health.get("statistics", {})
    logger.info(f"Final statistics: {stats}")
    
    # Check for significant leaks (allow some margin for logging, etc.)
    if fd_diff > 10:
        logger.warning(f"Potential file descriptor leak: {fd_diff} extra descriptors")
        return False
    else:
        logger.info("✅ No significant file descriptor leak detected")
        return True


async def test_concurrent_servers():
    """Test concurrent server operations."""
    logger.info("Testing concurrent server operations")
    
    client = MCPClient()
    initial_fds = count_open_files()
    
    # Create multiple servers concurrently
    configs = [
        MCPServerConfig(f"concurrent_{i}", "/bin/echo", [f"server_{i}"], timeout=2)
        for i in range(3)
    ]
    
    # Add all servers concurrently
    logger.info("Adding servers concurrently...")
    tasks = [client.add_server(config) for config in configs]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Server {i} failed: {result}")
        else:
            logger.info(f"Server {i}: {'SUCCESS' if result else 'FAILED'}")
    
    # Check status
    health = await client.health_check()
    logger.info(f"Active servers: {len(health.get('servers', {}))}")
    
    # Remove all servers concurrently
    logger.info("Removing servers concurrently...")
    remove_tasks = [client.remove_server(f"concurrent_{i}") for i in range(3)]
    await asyncio.gather(*remove_tasks, return_exceptions=True)
    
    await client.shutdown()
    
    final_fds = count_open_files()
    logger.info(f"Concurrent test FD change: {final_fds - initial_fds}")


if __name__ == "__main__":
    async def main():
        logger.info("🧪 Starting lite memory leak tests")
        
        try:
            # Test 1: Basic lifecycle
            lifecycle_ok = await test_mcp_server_lifecycle()
            
            # Test 2: Concurrent operations
            await test_concurrent_servers()
            
            if lifecycle_ok:
                logger.info("✅ All tests PASSED - No significant memory leaks detected")
                return 0
            else:
                logger.error("❌ Tests FAILED - Potential memory leak detected")
                return 1
                
        except Exception as e:
            logger.error(f"Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
