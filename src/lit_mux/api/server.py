"""
FastAPI REST API server for lit-mux.
Includes MCP tool integration and enhanced AI capabilities.
"""

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime

from ..core.session import SessionManager, Session, Message
from ..core.router import MessageRouter
from ..services.mcp_client import MCPClient, MCPServerConfig
from ..services.tool_processor import ToolCallProcessor
from ..services.prompt_composer import PromptComposer

logger = logging.getLogger(__name__)


# Pydantic models for API requests/responses
class CreateSessionRequest(BaseModel):
    backends: List[str] = Field(..., description="List of backend names to use")
    name: Optional[str] = Field(None, description="Optional session name")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class SendMessageRequest(BaseModel):
    content: str = Field(..., description="Message content to send")
    backend: Optional[str] = Field(None, description="Specific backend to use")
    model: Optional[str] = Field(None, description="Specific model to use (backend-dependent)")
    use_tools: Optional[bool] = Field(True, description="Enable tool calling for this message")
    max_tool_iterations: Optional[int] = Field(20, description="Maximum tool call iterations")


class BroadcastMessageRequest(BaseModel):
    content: str = Field(..., description="Message content to broadcast")
    backends: Optional[List[str]] = Field(None, description="Backends to broadcast to")


class MessageResponse(BaseModel):
    id: str
    content: str
    role: str
    backend: str
    model: Optional[str] = Field(None, description="Model used to generate response")
    timestamp: datetime
    metadata: Dict[str, Any]


class SessionResponse(BaseModel):
    id: str
    name: Optional[str]
    backends: List[str]
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]
    message_count: int


class BackendStatus(BaseModel):
    name: str
    enabled: bool
    healthy: bool


class LitMuxAPI:
    """FastAPI application for lit-mux."""
    
    def __init__(self):
        from ..core.config import load_config
        self.config = load_config()
        
        self.app = FastAPI(
            title="LIT Mux API",
            description="Multi-AI multiplexer REST API with MCP tool integration",
            version="0.1.0"
        )
        
        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Configure appropriately for production
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Initialize core components
        self.session_manager = SessionManager()
        self.message_router = MessageRouter()
        
        # Initialize MCP client and tool processing
        self.mcp_client = MCPClient()
        self.prompt_composer = PromptComposer()
        
        # Setup routes
        self._setup_routes()
    
    def _check_auth(self, request: Request):
        """Check API key authentication."""
        if not self.config.server.api_key:
            return True  # No auth required if no key configured
            
        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")
        if api_key != self.config.server.api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
        return True
    
    async def initialize_mcp(self, server_configs: List[MCPServerConfig] = None):
        """Initialize MCP servers. Called by the main server setup."""
        if server_configs:
            for config in server_configs:
                await self.mcp_client.add_server(config)
                logger.info(f"Added MCP server: {config.name}")
    
    async def shutdown_mcp(self):
        """Shutdown MCP servers."""
        await self.mcp_client.shutdown()
    
    def _setup_routes(self):
        """Setup API routes."""
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "healthy", "timestamp": datetime.now()}
        
        @self.app.post("/sessions", response_model=SessionResponse)
        async def create_session(request: CreateSessionRequest, auth=Depends(self._check_auth)):
            """Create a new AI session."""
            # Validate backends exist
            available_backends = self.message_router.list_backends()
            invalid_backends = [b for b in request.backends if b not in available_backends]
            if invalid_backends:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid backends: {invalid_backends}"
                )
            
            session = await self.session_manager.create_session(
                backends=request.backends,
                name=request.name,
                metadata=request.metadata
            )
            
            return SessionResponse(
                id=session.id,
                name=session.name,
                backends=session.backends,
                created_at=session.created_at,
                updated_at=session.updated_at,
                metadata=session.metadata,
                message_count=len(session.messages)
            )
        
        @self.app.get("/sessions", response_model=List[SessionResponse])
        async def list_sessions(auth=Depends(self._check_auth)):
            """List all sessions."""
            sessions = await self.session_manager.list_sessions()
            return [
                SessionResponse(
                    id=session.id,
                    name=session.name,
                    backends=session.backends,
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                    metadata=session.metadata,
                    message_count=len(session.messages)
                )
                for session in sessions
            ]
        
        @self.app.get("/sessions/{session_id}", response_model=SessionResponse)
        async def get_session(session_id: str, auth=Depends(self._check_auth)):
            """Get session details."""
            session = await self.session_manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            
            return SessionResponse(
                id=session.id,
                name=session.name,
                backends=session.backends,
                created_at=session.created_at,
                updated_at=session.updated_at,
                metadata=session.metadata,
                message_count=len(session.messages)
            )
        
        @self.app.delete("/sessions/{session_id}")
        async def delete_session(session_id: str, auth=Depends(self._check_auth)):
            """Delete a session."""
            success = await self.session_manager.delete_session(session_id)
            if not success:
                raise HTTPException(status_code=404, detail="Session not found")
            return {"message": "Session deleted"}
        
        @self.app.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
        async def get_session_messages(session_id: str, auth=Depends(self._check_auth)):
            """Get all messages from a session."""
            session = await self.session_manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            
            return [
                MessageResponse(
                    id=msg.id,
                    content=msg.content,
                    role=msg.role,
                    backend=msg.backend,
                    model=msg.metadata.get("model"),
                    timestamp=msg.timestamp,
                    metadata=msg.metadata
                )
                for msg in session.messages
            ]
        
        @self.app.post("/sessions/{session_id}/message", response_model=MessageResponse)
        async def send_message(session_id: str, request: SendMessageRequest, auth=Depends(self._check_auth)):
            """Send a message to a session with optional tool support."""
            session = await self.session_manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            
            # Determine backend to use
            backend = request.backend or session.backends[0]
            if backend not in session.backends:
                raise HTTPException(
                    status_code=400,
                    detail=f"Backend {backend} not available in this session"
                )
            
            # Add user message to session
            user_msg = await self.session_manager.add_message_to_session(
                session_id, request.content, "user", "client"
            )
            
            # Get session message history for context
            messages = []
            for msg in session.messages[-10:]:  # Last 10 messages for context
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
            
            # Get backend instance
            backend_instance = self.message_router.get_backend(backend)
            if not backend_instance:
                raise HTTPException(
                    status_code=500,
                    detail=f"Backend {backend} not available"
                )
            
            # Determine model to use
            model = request.model or backend_instance.default_model
            
            # Check if we should use tools
            use_tools = request.use_tools and bool(self.mcp_client.get_available_tools())
            
            if use_tools:
                # Use tool-enhanced processing
                available_tools = self.mcp_client.get_available_tools()
                logger.info(f"Processing message with tools enabled using model {model}")
                logger.info(f"Available tools: {[t.name for t in available_tools]}")
                
                # Initialize tool processor
                tool_processor = ToolCallProcessor(self.mcp_client, backend_instance)
                
                # Compose system prompt with tools
                prompt_info = self.prompt_composer.compose_system_prompt(
                    request.content,
                    available_tools,
                    messages
                )
                
                logger.info(f"System prompt composed: {len(prompt_info['system_prompt'])} chars")
                logger.info(f"System prompt preview: {prompt_info['system_prompt'][:500]}...")
                
                # Add system prompt to messages
                enhanced_messages = [
                    {"role": "system", "content": prompt_info["system_prompt"]}
                ] + messages
                
                # Process with tools
                response_content = await tool_processor.process_with_tools(
                    model=model,
                    messages=enhanced_messages,
                    tools=[],  # Tools are in system prompt
                    max_iterations=request.max_tool_iterations,
                    system_prompt_info=prompt_info
                )
                
                response_model = model
                
            else:
                # Standard processing without tools
                if request.use_tools:
                    logger.warning(f"Tools requested but no tools available. Available: {len(self.mcp_client.get_available_tools())}")
                logger.info(f"Processing message without tools using model {model}")
                
                kwargs = {
                    "session_metadata": session.metadata
                }
                if request.model:
                    kwargs["model"] = request.model
                
                response = await self.message_router.send_message(
                    backend, request.content, context=[], **kwargs
                )
                
                if response is None:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to get response from backend {backend}"
                    )
                
                # Extract content and model from response
                response_content = response.get("content", "")
                response_model = response.get("model")
            
            # Add AI response to session with model info
            ai_msg_metadata = {"model": response_model} if response_model else {}
            ai_msg = await self.session_manager.add_message_to_session(
                session_id, response_content, "assistant", backend, ai_msg_metadata
            )
            
            return MessageResponse(
                id=ai_msg.id,
                content=ai_msg.content,
                role=ai_msg.role,
                backend=ai_msg.backend,
                model=response_model,
                timestamp=ai_msg.timestamp,
                metadata=ai_msg.metadata
            )
        
        @self.app.post("/sessions/{session_id}/broadcast")
        async def broadcast_message(session_id: str, request: BroadcastMessageRequest, auth=Depends(self._check_auth)):
            """Broadcast message to multiple backends."""
            session = await self.session_manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            
            # Determine backends to use
            backends = request.backends or session.backends
            invalid_backends = [b for b in backends if b not in session.backends]
            if invalid_backends:
                raise HTTPException(
                    status_code=400,
                    detail=f"Backends not available in session: {invalid_backends}"
                )
            
            # Add user message
            await self.session_manager.add_message_to_session(
                session_id, request.content, "user", "client"
            )
            
            # Broadcast to backends
            responses = await self.message_router.broadcast_message(
                backends, request.content, context=[]
            )
            
            # Add all responses to session
            results = []
            for backend, response in responses.items():
                if response is not None:
                    ai_msg = await self.session_manager.add_message_to_session(
                        session_id, response, "assistant", backend
                    )
                    results.append({
                        "backend": backend,
                        "message": MessageResponse(
                            id=ai_msg.id,
                            content=ai_msg.content,
                            role=ai_msg.role,
                            backend=ai_msg.backend,
                            timestamp=ai_msg.timestamp,
                            metadata=ai_msg.metadata
                        )
                    })
                else:
                    results.append({
                        "backend": backend,
                        "error": "Failed to get response"
                    })
            
            return {"responses": results}
        
        @self.app.get("/backends", response_model=List[BackendStatus])
        async def list_backends(auth=Depends(self._check_auth)):
            """List all available backends."""
            backend_names = self.message_router.list_backends()
            health_status = await self.message_router.health_check_all()
            
            return [
                BackendStatus(
                    name=name,
                    enabled=self.message_router.get_backend(name).enabled,
                    healthy=health_status.get(name, False)
                )
                for name in backend_names
            ]
        
        @self.app.get("/tools")
        async def list_mcp_tools(auth=Depends(self._check_auth)):
            """List all available MCP tools."""
            tools = self.mcp_client.get_available_tools()
            return {
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "server": tool.server_name,
                        "parameters": tool.parameters
                    }
                    for tool in tools
                ],
                "total": len(tools)
            }
        
        @self.app.get("/mcp/health")
        async def mcp_health_check(auth=Depends(self._check_auth)):
            """Check MCP server health status and clean up dead servers."""
            health_info = await self.mcp_client.health_check()
            
            # Check for dead servers and clean them up
            dead_servers = []
            for server_name, info in health_info.get("servers", {}).items():
                if not info.get("running", False):
                    server = self.mcp_client.servers.get(server_name)
                    if server and server.process and server.process.poll() is not None:
                        logger.warning(f"Detected dead server {server_name}, cleaning up")
                        await self.mcp_client.remove_server(server_name)
                        dead_servers.append(server_name)
            
            if dead_servers:
                # Refresh health info after cleanup
                health_info = await self.mcp_client.health_check()
                health_info["cleaned_up"] = dead_servers
            
            return health_info
        
        @self.app.get("/models")
        async def list_models(auth=Depends(self._check_auth)):
            """Get available models from all backends."""
            models = {}
            
            # Get models from each backend
            for backend_name in self.message_router.list_backends():
                backend = self.message_router.get_backend(backend_name)
                if hasattr(backend, 'get_models'):
                    try:
                        backend_models = await backend.get_models()
                        models[backend_name] = [
                            {
                                "name": model.name,
                                "display_name": model.display_name,
                                "size_mb": round(model.size_mb, 1) if hasattr(model, 'size_mb') else None,
                                "digest": getattr(model, 'digest', None)
                            }
                            for model in backend_models
                        ]
                    except Exception as e:
                        logger.error(f"Failed to get models from {backend_name}: {e}")
                        models[backend_name] = []
                else:
                    models[backend_name] = []
            
            return {
                "models": models,
                "total": sum(len(backend_models) for backend_models in models.values())
            }
