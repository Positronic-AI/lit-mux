#!/usr/bin/env python3
"""
Monitor script to watch lit-mux server for file descriptor leaks.
Run this in parallel with your lit-mux server to monitor resource usage.
"""

import time
import subprocess
import psutil
import sys
from datetime import datetime


def find_lit_mux_process():
    """Find running lit-mux process."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'lit-mux' in cmdline or 'lit_mux' in cmdline:
                return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def get_fd_count(pid):
    """Get file descriptor count for a process."""
    try:
        proc = psutil.Process(pid)
        return len(proc.open_files()) + len(proc.connections())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return -1


def get_memory_info(pid):
    """Get memory usage info for a process."""
    try:
        proc = psutil.Process(pid)
        mem_info = proc.memory_info()
        return {
            'rss': mem_info.rss / 1024 / 1024,  # MB
            'vms': mem_info.vms / 1024 / 1024,  # MB
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def monitor_lit_mux():
    """Monitor lit-mux process for resource leaks."""
    print("🔍 Looking for lit-mux process...")
    
    pid = find_lit_mux_process()
    if not pid:
        print("❌ No lit-mux process found. Start lit-mux first.")
        return
    
    print(f"✅ Found lit-mux process: PID {pid}")
    print("📊 Starting monitoring... (Press Ctrl+C to stop)")
    print()
    print(f"{'Time':<20} {'FDs':<8} {'RSS(MB)':<10} {'VMS(MB)':<10} {'Status'}")
    print("-" * 65)
    
    initial_fd_count = get_fd_count(pid)
    max_fd_count = initial_fd_count
    measurements = []
    
    try:
        while True:
            fd_count = get_fd_count(pid)
            if fd_count == -1:
                print(f"❌ Process {pid} no longer exists")
                break
            
            mem_info = get_memory_info(pid)
            if not mem_info:
                print(f"❌ Can't get memory info for process {pid}")
                break
            
            # Track maximums
            if fd_count > max_fd_count:
                max_fd_count = fd_count
            
            # Status indicators
            status_indicators = []
            if fd_count > initial_fd_count + 50:
                status_indicators.append("🚨LEAK")
            elif fd_count > initial_fd_count + 20:
                status_indicators.append("⚠️HIGH")
            elif fd_count > max_fd_count * 0.9:
                status_indicators.append("📈RISING")
            else:
                status_indicators.append("✅OK")
            
            status = " ".join(status_indicators)
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"{timestamp:<20} {fd_count:<8} {mem_info['rss']:<10.1f} {mem_info['vms']:<10.1f} {status}")
            
            # Store measurement
            measurements.append({
                'timestamp': timestamp,
                'fd_count': fd_count,
                'rss': mem_info['rss'],
                'vms': mem_info['vms']
            })
            
            # Keep last 100 measurements
            if len(measurements) > 100:
                measurements.pop(0)
            
            time.sleep(5)  # Check every 5 seconds
            
    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped")
        
        # Summary
        if measurements:
            final_fd = measurements[-1]['fd_count']
            fd_change = final_fd - initial_fd_count
            avg_fd = sum(m['fd_count'] for m in measurements) / len(measurements)
            
            print("\n📋 Summary:")
            print(f"   Initial FDs: {initial_fd_count}")
            print(f"   Final FDs: {final_fd}")
            print(f"   Maximum FDs: {max_fd_count}")
            print(f"   Average FDs: {avg_fd:.1f}")
            print(f"   Net change: {fd_change:+d}")
            print(f"   Measurements: {len(measurements)}")
            
            if fd_change > 50:
                print("   🚨 SIGNIFICANT LEAK DETECTED")
            elif fd_change > 20:
                print("   ⚠️ POSSIBLE LEAK")
            elif fd_change > 10:
                print("   📈 SLIGHT INCREASE")
            else:
                print("   ✅ NO SIGNIFICANT LEAK")


def test_health_endpoint():
    """Test the MCP health endpoint to trigger cleanup."""
    try:
        import requests
        response = requests.get("http://127.0.0.1:8000/mcp/health", timeout=5)
        if response.status_code == 200:
            health_data = response.json()
            print(f"🏥 Health check: {len(health_data.get('servers', {}))} servers")
            if 'cleaned_up' in health_data:
                print(f"🧹 Cleaned up dead servers: {health_data['cleaned_up']}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Health check error: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "health":
        test_health_endpoint()
    else:
        monitor_lit_mux()
