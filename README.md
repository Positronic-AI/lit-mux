# LIT Mux

Multi-AI multiplexer with REST API for universal AI backend management.

## 🚀 Quick Start

```bash
# Installation
pip install lit-mux

# Initialize configuration
lit-mux init

# Start the server
lit-mux start

# Check status
lit-mux status
```

## 🎯 Features

- **Universal AI Backend Support**: Claude Desktop, ChatGPT API, Ollama, self-hosted models
- **REST API Interface**: Clean HTTP endpoints for any client language
- **Session Management**: Persistent conversations across AI backends
- **Multi-AI Broadcasting**: Send messages to multiple AIs simultaneously
- **Plugin Architecture**: Easy backend and client extensibility
- **Service Management**: Built-in service installation and management

## 🏗️ Architecture

```
Client Applications
       ↓ HTTP REST API
    lit-mux Core
       ↓ Backend Plugins  
[Claude] [ChatGPT] [Ollama] [Custom]
```

## 📡 API Endpoints

### Sessions
- `POST /sessions` - Create new session
- `GET /sessions` - List sessions  
- `GET /sessions/{id}` - Get session details
- `DELETE /sessions/{id}` - Delete session

### Messages
- `POST /sessions/{id}/message` - Send message to session
- `POST /sessions/{id}/broadcast` - Send to multiple backends
- `GET /sessions/{id}/messages` - Get conversation history

### Backends
- `GET /backends` - List available backends
- `POST /backends/{id}/configure` - Configure backend
- `GET /backends/{id}/status` - Check backend health

## 🔧 Configuration

lit-mux uses configuration files in `~/.config/lit-mux/`:

```yaml
# config.yaml
backends:
  ollama:
    enabled: true
    host: "http://localhost:11434"
    default_model: "llama3.1"
  
  chatgpt:
    enabled: true
    api_key: "${OPENAI_API_KEY}"
    model: "gpt-4"
  
  claude_desktop:
    enabled: true
    automation: true

server:
  host: "127.0.0.1"
  port: 8000
  log_level: "info"
```

## 🛠️ Development

```bash
# Clone repository
git clone https://github.com/Positronic-AI/lit-mux.git
cd lit-mux

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Start development server
lit-mux-server --reload
```

## 📝 License

MIT License - see [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions welcome! Please see our contributing guidelines.

---

**Made with ❤️ by [LIT](https://lit.ai) - Advancing AI through open-source innovation**
