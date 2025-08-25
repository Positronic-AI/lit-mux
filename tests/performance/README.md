# Performance Tests

Performance, load testing, and memory leak tests for lit-mux.

## Files

- **stress_test_mcp.py** - MCP stress testing
- **test_leak_fix.py** - Memory leak fix verification
- **test_leak_simple.py** - Simple memory leak test

## Usage

```bash
# Run stress tests
python tests/performance/stress_test_mcp.py

# Run memory leak tests
python tests/performance/test_leak_simple.py
python tests/performance/test_leak_fix.py
```
