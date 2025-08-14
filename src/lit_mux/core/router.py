"""
Message routing core for lit-mux.
Handles routing messages between clients and AI backends.
"""

import asyncio
from typing import Dict, List, Optional, Any, Callable
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class Backend(ABC):
    """Abstract base class for AI backends."""
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.enabled = True
    
    @abstractmethod
    async def send_message(self, content: str, context: List[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """Send a message to the AI backend and return response with metadata."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the backend is healthy and responsive."""
        pass
    
    async def configure(self, config: Dict[str, Any]) -> None:
        """Update backend configuration."""
        self.config.update(config)


class MessageRouter:
    """Routes messages between clients and AI backends."""
    
    def __init__(self):
        self._backends: Dict[str, Backend] = {}
        self._middleware: List[Callable] = []
    
    def register_backend(self, backend: Backend) -> None:
        """Register an AI backend."""
        self._backends[backend.name] = backend
        logger.info(f"Registered backend: {backend.name}")
    
    def get_backend(self, name: str) -> Optional[Backend]:
        """Get a backend by name."""
        return self._backends.get(name)
    
    def list_backends(self) -> List[str]:
        """List all registered backend names."""
        return list(self._backends.keys())
    
    def get_enabled_backends(self) -> List[str]:
        """Get list of enabled backend names."""
        return [name for name, backend in self._backends.items() if backend.enabled]
    
    async def send_message(
        self, 
        backend_name: str, 
        content: str, 
        context: List[Dict[str, Any]] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Send message to a specific backend."""
        backend = self.get_backend(backend_name)
        if not backend:
            logger.error(f"Backend not found: {backend_name}")
            return None
        
        if not backend.enabled:
            logger.warning(f"Backend disabled: {backend_name}")
            return None
        
        try:
            response = await backend.send_message(content, context, **kwargs)
            
            # Handle both old string responses and new dict responses
            if isinstance(response, dict):
                return response
            elif isinstance(response, str):
                return {"content": response, "model": None}
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error sending message to {backend_name}: {e}")
            return None
    
    async def broadcast_message(
        self, 
        backend_names: List[str], 
        content: str, 
        context: List[Dict[str, Any]] = None
    ) -> Dict[str, Optional[str]]:
        """Send message to multiple backends simultaneously."""
        tasks = []
        for backend_name in backend_names:
            task = asyncio.create_task(
                self.send_message(backend_name, content, context)
            )
            tasks.append((backend_name, task))
        
        results = {}
        for backend_name, task in tasks:
            try:
                response = await task
                results[backend_name] = response
            except Exception as e:
                logger.error(f"Broadcast error for {backend_name}: {e}")
                results[backend_name] = None
        
        return results
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all backends."""
        results = {}
        for name, backend in self._backends.items():
            try:
                results[name] = await backend.health_check()
            except Exception as e:
                logger.error(f"Health check failed for {name}: {e}")
                results[name] = False
        return results
