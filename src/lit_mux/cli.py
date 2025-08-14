"""
Command-line interface for lit-mux.
"""

import click
import asyncio
import uvicorn
from pathlib import Path
import os
import sys

from .api.server import LitMuxAPI
from .core.config import Config, load_config, create_default_config


@click.group()
@click.version_option()
def main():
    """LIT Mux - Multi-AI multiplexer with REST API."""
    pass


@main.command()
def init():
    """Initialize lit-mux configuration."""
    config_dir = Path.home() / ".config" / "lit-mux"
    config_file = config_dir / "config.yaml"
    
    if config_file.exists():
        click.echo(f"Configuration already exists at {config_file}")
        return
    
    # Create config directory
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # Create default configuration
    create_default_config(config_file)
    
    click.echo(f"✅ Created configuration at {config_file}")
    click.echo("Edit the configuration file to customize your backends.")


@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def start(host: str, port: int, reload: bool):
    """Start the lit-mux server."""
    config = load_config()
    
    # Override with CLI options
    host = host or config.server.host
    port = port or config.server.port
    
    click.echo(f"🚀 Starting lit-mux server on {host}:{port}")
    
    uvicorn.run(
        "lit_mux.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )


@main.command()
def status():
    """Check lit-mux server status."""
    import requests
    
    config = load_config()
    url = f"http://{config.server.host}:{config.server.port}/health"
    
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            click.echo("✅ lit-mux server is running")
            data = response.json()
            click.echo(f"   Status: {data.get('status')}")
            click.echo(f"   Timestamp: {data.get('timestamp')}")
        else:
            click.echo("❌ lit-mux server returned error")
    except requests.exceptions.ConnectionError:
        click.echo("❌ lit-mux server is not running")
    except Exception as e:
        click.echo(f"❌ Error checking status: {e}")


@main.command()
@click.argument("message")
@click.option("--backend", help="Specific backend to use")
@click.option("--session", help="Session ID to use")
def send(message: str, backend: str, session: str):
    """Send a message directly via CLI."""
    import requests
    
    config = load_config()
    base_url = f"http://{config.server.host}:{config.server.port}"
    
    try:
        # Create session if not provided
        if not session:
            backends = [backend] if backend else ["ollama"]  # Default backend
            response = requests.post(f"{base_url}/sessions", json={
                "backends": backends,
                "name": "CLI Session"
            })
            session = response.json()["id"]
            click.echo(f"Created session: {session}")
        
        # Send message
        payload = {"content": message}
        if backend:
            payload["backend"] = backend
            
        response = requests.post(f"{base_url}/sessions/{session}/message", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            click.echo(f"\n{data['backend']}: {data['content']}")
        else:
            click.echo(f"❌ Error: {response.json().get('detail', 'Unknown error')}")
            
    except Exception as e:
        click.echo(f"❌ Error: {e}")


@main.command()
def backends():
    """List available backends."""
    import requests
    
    config = load_config()
    url = f"http://{config.server.host}:{config.server.port}/backends"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            backends = response.json()
            click.echo("Available backends:")
            for backend in backends:
                status = "✅" if backend["enabled"] and backend["healthy"] else "❌"
                click.echo(f"  {status} {backend['name']}")
        else:
            click.echo("❌ Error fetching backends")
    except Exception as e:
        click.echo(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
