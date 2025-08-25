# Testing the Memory Leak Fix

The memory leak causing "Too many open files" in lit-mux has been fixed. Here's how to test and verify the fix:

## Quick Verification

1. **Test the MCP client directly** (no dependencies needed):
   ```bash
   cd /home/ben/lit-platform/lit-mux
   python3 test_leak_simple.py
   ```
   
   This should show stable file descriptor counts and pass all tests.

## Testing with Running Server

1. **Start lit-mux server**:
   ```bash
   cd /home/ben/lit-platform/lit-mux
   # Install dependencies if needed:
   pip install fastapi uvicorn pydantic requests aiofiles python-multipart click rich toml
   
   # Start server
   python3 -m lit_mux.server
   ```

2. **Monitor resources** (in another terminal):
   ```bash
   cd /home/ben/lit-platform/lit-mux
   python3 monitor_resources.py
   ```
   
   This will show real-time file descriptor and memory usage.

3. **Run stress test** (in another terminal):
   ```bash
   cd /home/ben/lit-platform/lit-mux
   pip install aiohttp  # if not already installed
   python3 stress_test_mcp.py
   ```
   
   This simulates the problematic scenario with repeated server creation attempts.

## What Should Happen

### Before the Fix:
- File descriptors would continuously increase
- Eventually hit system limits (errno 24: Too many open files)
- Server would become unresponsive

### After the Fix:
- File descriptors remain stable
- Failed server attempts are properly cleaned up
- Server continues running indefinitely
- Health endpoint shows proper statistics

## Expected Test Results

### test_leak_simple.py:
```
✅ No significant file descriptor leak detected
✅ All tests PASSED - No significant memory leaks detected
```

### monitor_resources.py:
```
Time                 FDs      RSS(MB)    VMS(MB)    Status
20:30:15            150      45.2       180.1      ✅OK
20:30:20            150      45.3       180.1      ✅OK
20:30:25            151      45.2       180.1      ✅OK
```

### stress_test_mcp.py:
```
📊 Final Statistics:
   Total server attempts: 60
   Failed attempts: 60
   Active servers: 0
   ✅ No servers remaining (good cleanup)
```

## Key Indicators of Success

1. **Stable file descriptors**: FD count doesn't continuously increase
2. **No "Too many open files" errors**: Server runs without errno 24
3. **Proper cleanup**: Failed servers don't accumulate
4. **Statistics tracking**: Health endpoint shows accurate counts

## Files Changed

- `src/lit_mux/services/mcp_client.py` - Main fixes for resource leaks
- `src/lit_mux/api/server.py` - Enhanced endpoints and error handling  
- `src/lit_mux/server.py` - Better shutdown handling

## Monitoring Commands

Check active processes:
```bash
ps aux | grep lit-mux
lsof -p <PID> | wc -l  # Count open file descriptors
```

Test health endpoint:
```bash
curl http://127.0.0.1:8000/mcp/health
```

If the stress test runs without causing "Too many open files" errors, the fix is working correctly!
