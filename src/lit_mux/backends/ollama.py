"""
Proven Ollama client service from lit-tui.
Handles model management, chat completion, and streaming responses.
Now includes MCP tool integration for enhanced AI capabilities.
"""

import asyncio
import logging
from typing import AsyncIterator, Dict, List, Optional, Any, Callable

import ollama
from ollama import AsyncClient

from ..core.router import Backend


logger = logging.getLogger(__name__)


class OllamaModel:
    """Represents an Ollama model."""
    
    def __init__(self, name: str, size: int = 0, digest: str = "", details: Optional[Dict] = None):
        self.name = name
        self.size = size
        self.digest = digest
        self.details = details or {}
        
    @property
    def display_name(self) -> str:
        """Get a user-friendly display name."""
        # Remove :latest suffix for cleaner display
        name = self.name.replace(":latest", "")
        
        # Capitalize first letter
        return name.capitalize()
    
    @property
    def size_mb(self) -> float:
        """Get model size in MB."""
        return self.size / (1024 * 1024)
    
    def __str__(self) -> str:
        return f"{self.display_name} ({self.size_mb:.1f}MB)"


class OllamaBackend(Backend):
    """Ollama backend adapted from lit-tui's proven OllamaClient."""
    
    def __init__(self, host: str = "http://localhost:11434", default_model: str = "llama3.1"):
        super().__init__("ollama")
        self.host = host
        self.default_model = default_model
        self.client = AsyncClient(host=host)
        self._models_cache: Optional[List[OllamaModel]] = None
        self._cache_time: Optional[float] = None
        
    async def send_message(self, content: str, context: List[Dict[str, Any]] = None, **kwargs) -> str:
        """Send message to Ollama and return response."""
        # Build messages from context
        messages = []
        if context:
            for msg in context:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
        # Add current message
        messages.append({
            "role": "user", 
            "content": content
        })
        
        # Determine model to use (priority: message > session > backend config > default)
        model = (
            kwargs.get("model") or  # Per-message model
            kwargs.get("session_metadata", {}).get("ollama_model") or  # Per-session model
            self.config.get("model") or  # Backend config model
            self.default_model  # Default fallback
        )
        
        logger.debug(f"Using ollama model: {model}")
        
        try:
            response = await self.client.chat(
                model=model,
                messages=messages,
                stream=False
            )
            
            if 'message' in response and 'content' in response['message']:
                # Return both content and metadata about the model used
                return {
                    "content": response['message']['content'],
                    "model": model
                }
            else:
                return None
                
        except Exception as e:
            logger.error(f"Ollama chat completion failed with model {model}: {e}")
            return None
    
    async def health_check(self) -> bool:
        """Check if Ollama is running and responsive."""
        try:
            await self.client.list()
            return True
        except Exception as e:
            logger.debug(f"Ollama health check failed: {e}")
            return False
    
    async def get_models(self, force_refresh: bool = False) -> List[OllamaModel]:
        """Get list of available models."""
        # Use cache if recent (within 30 seconds)
        current_time = asyncio.get_event_loop().time()
        if (not force_refresh and 
            self._models_cache is not None and 
            self._cache_time is not None and 
            current_time - self._cache_time < 30):
            return self._models_cache
        
        try:
            response = await self.client.list()
            models = []
            
            for model_data in response.get('models', []):
                # Handle both direct name field and nested structure
                model_name = model_data.get('model') or model_data.get('name', '')
                
                if not model_name:
                    logger.warning(f"Model data missing name: {model_data}")
                    continue
                
                model = OllamaModel(
                    name=model_name,
                    size=model_data.get('size', 0),
                    digest=model_data.get('digest', ''),
                    details=model_data.get('details', {})
                )
                models.append(model)
            
            # Cache the results
            self._models_cache = models
            self._cache_time = current_time
            
            logger.info(f"Found {len(models)} Ollama models")
            return models
            
        except Exception as e:
            logger.error(f"Failed to fetch models: {e}")
            return []
    
    async def stream_chat(
        self,
        content: str,
        context: List[Dict[str, Any]] = None
    ) -> AsyncIterator[str]:
        """Stream chat completion (for future streaming API support)."""
        # Build messages from context
        messages = []
        if context:
            for msg in context:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
        # Add current message
        messages.append({
            "role": "user", 
            "content": content
        })
        
        model = self.config.get("model", self.default_model)
        
        try:
            async for chunk in await self.client.chat(
                model=model,
                messages=messages,
                stream=True
            ):
                if 'message' in chunk and 'content' in chunk['message']:
                    content = chunk['message']['content']
                    if content:  # Only yield non-empty content
                        yield content
                        
        except Exception as e:
            logger.error(f"Streaming chat failed: {e}")
            yield f"\nError: {e}"

    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        options: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[str]:
        """
        Chat completion method compatible with tool processor.
        This method is used by the ToolCallProcessor.
        """
        try:
            # Use the configured Ollama client
            response = await self.client.chat(
                model=model,
                messages=messages,
                stream=stream,
                options=options or {}
            )
            
            if stream:
                # For streaming, yield content as it comes
                async for chunk in response:
                    if 'message' in chunk and 'content' in chunk['message']:
                        content = chunk['message']['content']
                        if content:
                            yield content
            else:
                # For non-streaming, return the full response
                if 'message' in response and 'content' in response['message']:
                    yield response['message']['content']
                    
        except Exception as e:
            logger.error(f"Chat completion failed: {e}")
            yield f"Error: {e}"
