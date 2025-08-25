#!/usr/bin/env python3
"""
Stress test for lit-mux MCP server management.
This simulates the problematic scenario that was causing "Too many open files".
"""

import asyncio
import aiohttp
import json
import time
import sys
from datetime import datetime


async def add_mcp_server(session, server_config):
    """Add an MCP server via API."""
    try:
        async with session.post(
            "http://127.0.0.1:8000/mcp/servers",
            json=server_config,
            headers={"Content-Type": "application/json"},
            timeout=10
        ) as response:
            result = await response.json()
            return response.status == 200, result
    except Exception as e:
        return False, str(e)


async def remove_mcp_server(session, server_name):
    """Remove an MCP server via API."""
    try:
        async with session.delete(
            f"http://127.0.0.1:8000/mcp/servers/{server_name}",
            timeout=10
        ) as response:
            result = await response.json()
            return response.status == 200, result
    except Exception as e:
        return False, str(e)


async def get_health(session):
    """Get health status."""
    try:
        async with session.get(
            "http://127.0.0.1:8000/mcp/health",
            timeout=10
        ) as response:
            result = await response.json()
            return response.status == 200, result
    except Exception as e:
        return False, str(e)


async def stress_test_mcp_servers():
    """Stress test MCP server creation and removal."""
    print("🔥 Starting MCP server stress test")
    print("   This simulates the scenario that was causing 'Too many open files'")
    print()
    
    # Test configurations that will fail (simulating SkillsAI server attempts)
    failing_configs = [
        {
            "name": "SkillsAI",
            "command": "/non/existent/command",
            "args": [],
            "timeout": 5
        },
        {
            "name": "TestServer1",
            "command": "/bin/false",
            "args": [],
            "timeout": 5  
        },
        {
            "name": "TestServer2",
            "command": "/usr/bin/python3",
            "args": ["-c", "exit(1)"],
            "timeout": 5
        }
    ]
    
    total_attempts = 0
    total_failures = 0
    
    async with aiohttp.ClientSession() as session:
        print(f"{'Cycle':<6} {'Time':<8} {'Server':<12} {'Add':<6} {'Remove':<8} {'Health'}")
        print("-" * 60)
        
        for cycle in range(20):  # 20 cycles to simulate sustained load
            cycle_start = time.time()
            
            for config in failing_configs:
                server_name = config["name"]
                
                # Attempt to add server (this should fail but not leak)
                add_success, add_result = await add_mcp_server(session, config)
                total_attempts += 1
                if not add_success:
                    total_failures += 1
                
                # Brief pause
                await asyncio.sleep(0.1)
                
                # Try to remove (cleanup)  
                remove_success, remove_result = await remove_mcp_server(session, server_name)
                
                # Get health status
                health_success, health_result = await get_health(session)
                health_servers = len(health_result.get("servers", {})) if health_success else "?"
                
                # Display status
                elapsed = time.time() - cycle_start
                print(f"{cycle+1:<6} {elapsed:<8.2f} {server_name:<12} "
                      f"{'✅' if add_success else '❌':<6} "
                      f"{'✅' if remove_success else '❌':<8} "
                      f"{health_servers}")
                
                # Small delay between servers
                await asyncio.sleep(0.1)
            
            # Pause between cycles
            await asyncio.sleep(0.5)
        
        print("\n" + "="*60)
        print("📊 Final Statistics:")
        
        # Get final health status
        health_success, health_result = await get_health(session)
        if health_success:
            servers = health_result.get("servers", {})
            stats = health_result.get("statistics", {})
            cleaned_up = health_result.get("cleaned_up", [])
            
            print(f"   Total server attempts: {total_attempts}")
            print(f"   Failed attempts: {total_failures}")
            print(f"   Success rate: {((total_attempts-total_failures)/total_attempts*100):.1f}%")
            print(f"   Active servers: {len(servers)}")
            print(f"   Total tools: {health_result.get('total_tools', 0)}")
            
            if stats:
                print(f"   Servers created: {stats.get('servers_created', 0)}")
                print(f"   Servers failed: {stats.get('servers_failed', 0)}")
                print(f"   Servers removed: {stats.get('servers_removed', 0)}")
            
            if cleaned_up:
                print(f"   Auto-cleaned servers: {cleaned_up}")
            
            # Check for problems
            if len(servers) > 0:
                print("   ⚠️ WARNING: Servers still active (possible leak)")
            else:
                print("   ✅ No servers remaining (good cleanup)")
        
        print("\n🏁 Stress test completed")
        print("   If lit-mux is still running without 'Too many open files',")
        print("   then the memory leak fix is working correctly!")


if __name__ == "__main__":
    try:
        asyncio.run(stress_test_mcp_servers())
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)
