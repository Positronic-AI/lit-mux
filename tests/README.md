# LIT Mux HTTP Tests

This directory contains HTTP test files for the lit-mux REST API.

## Test Files

1. **01-health.http** - Basic health checks and backend discovery
2. **02-sessions.http** - Session creation, listing, and management
3. **03-messaging.http** - Send messages and test AI responses
4. **04-broadcast.http** - Multi-AI broadcasting (future feature)
5. **05-edge-cases.http** - Error handling and edge cases
6. **06-client-examples.http** - Real-world client integration examples

## How to Run Tests

### Option 1: VS Code REST Client Extension
1. Install the "REST Client" extension in VS Code
2. Open any `.http` file
3. Click "Send Request" above each request

### Option 2: IntelliJ HTTP Client
1. Open any `.http` file in IntelliJ/PyCharm
2. Click the green arrow next to each request

### Option 3: Command Line with curl

```bash
# Health check
curl http://127.0.0.1:8000/health

# List backends  
curl http://127.0.0.1:8000/backends

# Create session
curl -X POST http://127.0.0.1:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"backends": ["ollama"], "name": "Test Session"}'

# Send message (replace SESSION_ID)
curl -X POST http://127.0.0.1:8000/sessions/SESSION_ID/message \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello!"}'
```

## Prerequisites

1. **Start lit-mux server:**
   ```bash
   cd /home/ben/lit-platform/lit-mux
   source .venv/bin/activate
   lit-mux start
   ```

2. **Ensure Ollama is running (optional):**
   ```bash
   ollama serve
   ollama pull llama3.1  # if not already installed
   ```

## Test Workflow

1. **Start with health tests** (`01-health.http`) to ensure server is running
2. **Create sessions** (`02-sessions.http`) and note the session IDs
3. **Update session IDs** in other test files where marked `REPLACE_WITH_SESSION_ID`
4. **Run messaging tests** (`03-messaging.http`) to test AI responses
5. **Try client examples** (`06-client-examples.http`) for real-world scenarios

## Expected Results

- Health checks should return `200 OK`
- Backend list should show ollama as enabled/healthy
- Session creation should return session IDs
- Messages should get AI responses from ollama
- Error cases should return appropriate 4xx status codes

## Notes for Integration

- **Skills Analysis**: Use the patterns in `06-client-examples.http` for skill-based AI integration
- **Multi-AI Coordination**: Examples show how to coordinate multiple backends effectively
- **Session IDs**: Save these from session creation for subsequent requests
- **Error Handling**: Check `05-edge-cases.http` for proper error responses
