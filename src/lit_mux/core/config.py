"""
Configuration management for lit-mux.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml
import os


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    api_key: Optional[str] = None


@dataclass
class MCPServerConfigData:
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    timeout: int = 30


@dataclass
class MCPConfig:
    enabled: bool = False
    servers: List[MCPServerConfigData] = field(default_factory=list)


@dataclass
class OllamaConfig:
    enabled: bool = False
    host: str = "http://localhost:11434"
    default_model: str = "llama3.1"


@dataclass
class ChatGPTConfig:
    enabled: bool = False
    api_key: Optional[str] = None
    model: str = "gpt-4"
    base_url: str = "https://api.openai.com/v1"


@dataclass
class ClaudeDesktopConfig:
    enabled: bool = False
    automation: bool = True


@dataclass
class BackendsConfig:
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    chatgpt: ChatGPTConfig = field(default_factory=ChatGPTConfig)
    claude_desktop: ClaudeDesktopConfig = field(default_factory=ClaudeDesktopConfig)


@dataclass
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    backends: BackendsConfig = field(default_factory=BackendsConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)


def get_config_path() -> Path:
    """Get the configuration file path."""
    config_dir = Path.home() / ".config" / "lit-mux"
    return config_dir / "config.yaml"


def create_default_config(config_file: Path) -> None:
    """Create a default configuration file."""
    config_data = {
        "server": {
            "host": "127.0.0.1",
            "port": 8000,
            "log_level": "info",
            "api_key": "change-this"
        },
        "backends": {
            "ollama": {
                "enabled": True,
                "host": "http://localhost:11434",
                "default_model": "llama3.1"
            },
            "chatgpt": {
                "enabled": False,
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4"
            },
            "claude_desktop": {
                "enabled": False,
                "automation": True
            }
        }
    }
    
    with open(config_file, 'w') as f:
        yaml.dump(config_data, f, default_flow_style=False)


def expand_env_vars(data: Any) -> Any:
    """Recursively expand environment variables in configuration."""
    if isinstance(data, dict):
        return {k: expand_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [expand_env_vars(item) for item in data]
    elif isinstance(data, str) and data.startswith("${") and data.endswith("}"):
        env_var = data[2:-1]
        return os.getenv(env_var, data)
    else:
        return data


def load_config() -> Config:
    """Load configuration from file."""
    config_file = get_config_path()
    
    if not config_file.exists():
        # Create default config if it doesn't exist
        config_file.parent.mkdir(parents=True, exist_ok=True)
        create_default_config(config_file)
    
    with open(config_file, 'r') as f:
        data = yaml.safe_load(f)
    
    # Expand environment variables
    data = expand_env_vars(data)
    
    # Convert to config objects
    server_config = ServerConfig(**data.get("server", {}))
    
    backends_data = data.get("backends", {})
    ollama_config = OllamaConfig(**backends_data.get("ollama", {}))
    chatgpt_config = ChatGPTConfig(**backends_data.get("chatgpt", {}))
    claude_config = ClaudeDesktopConfig(**backends_data.get("claude_desktop", {}))
    
    backends_config = BackendsConfig(
        ollama=ollama_config,
        chatgpt=chatgpt_config,
        claude_desktop=claude_config
    )
    
    # Load MCP configuration
    mcp_data = data.get("mcp", {})
    mcp_servers = []
    for server_data in mcp_data.get("servers", []):
        server_config_data = MCPServerConfigData(
            name=server_data["name"],
            command=server_data["command"],
            args=server_data.get("args", []),
            env=server_data.get("env", {}),
            timeout=server_data.get("timeout", 30)
        )
        mcp_servers.append(server_config_data)
    
    mcp_config = MCPConfig(
        enabled=mcp_data.get("enabled", False),
        servers=mcp_servers
    )
    
    return Config(
        server=server_config,
        backends=backends_config,
        mcp=mcp_config
    )
