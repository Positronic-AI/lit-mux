"""
Server entry point for lit-mux.
"""

import uvicorn
import logging
from .api.server import LitMuxAPI
from .core.config import load_config
from .backends.ollama import OllamaBackend

logger = logging.getLogger(__name__)


def create_app():
    """Create and configure the FastAPI application."""
    # Load configuration
    config = load_config()
    
    # Create API instance
    api = LitMuxAPI()
    
    # Register backends based on configuration
    if config.backends.ollama.enabled:
        ollama_backend = OllamaBackend(
            host=config.backends.ollama.host,
            default_model=config.backends.ollama.default_model
        )
        api.message_router.register_backend(ollama_backend)
    
    # TODO: Add other backends (ChatGPT, Claude Desktop) when implemented
    
    return api


# Create the app instance for uvicorn
app_instance = create_app()
app = app_instance.app


@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    # Load MCP servers from configuration
    config = load_config()
    if config.mcp.enabled and config.mcp.servers:
        from .services.mcp_client import MCPServerConfig
        
        for server_config_data in config.mcp.servers:
            server_config = MCPServerConfig(
                name=server_config_data.name,
                command=server_config_data.command,
                args=server_config_data.args,
                env=server_config_data.env,
                timeout=server_config_data.timeout
            )
            await app_instance.mcp_client.add_server(server_config)
            logger.info(f"Loaded MCP server from config: {server_config.name}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup MCP servers on shutdown."""
    logger.info("Application shutting down, cleaning up MCP servers")
    try:
        await app_instance.shutdown_mcp()
    except Exception as e:
        logger.error(f"Error during MCP shutdown: {e}")
        # Force shutdown if graceful fails
        try:
            await app_instance.mcp_client.force_shutdown()
        except Exception as force_e:
            logger.error(f"Error during force shutdown: {force_e}")


def main():
    """Main entry point for lit-mux-server command."""
    config = load_config()
    
    uvicorn.run(
        "lit_mux.server:app",
        host=config.server.host,
        port=config.server.port,
        log_level=config.server.log_level
    )


if __name__ == "__main__":
    main()
