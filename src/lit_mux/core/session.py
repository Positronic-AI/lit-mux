"""
Core session management for lit-mux.
Handles creating, tracking, and managing AI conversation sessions.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import json


@dataclass
class Message:
    """A single message in a conversation."""
    id: str
    content: str
    role: str  # 'user', 'assistant', 'system'
    backend: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class Session:
    """An AI conversation session."""
    id: str
    name: Optional[str]
    backends: List[str]
    messages: List[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, content: str, role: str, backend: str, metadata: Dict[str, Any] = None) -> Message:
        """Add a message to the session."""
        message = Message(
            id=str(uuid.uuid4()),
            content=content,
            role=role,
            backend=backend,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
        self.messages.append(message)
        self.updated_at = datetime.now()
        return message


class SessionManager:
    """Manages AI conversation sessions."""
    
    def __init__(self):
        self._sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()
    
    async def create_session(
        self, 
        backends: List[str], 
        name: Optional[str] = None,
        metadata: Dict[str, Any] = None
    ) -> Session:
        """Create a new session."""
        async with self._lock:
            session_id = str(uuid.uuid4())
            session = Session(
                id=session_id,
                name=name,
                backends=backends,
                metadata=metadata or {}
            )
            self._sessions[session_id] = session
            return session
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self._sessions.get(session_id)
    
    async def list_sessions(self) -> List[Session]:
        """List all sessions."""
        return list(self._sessions.values())
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False
    
    async def add_message_to_session(
        self, 
        session_id: str, 
        content: str, 
        role: str, 
        backend: str,
        metadata: Dict[str, Any] = None
    ) -> Optional[Message]:
        """Add a message to a session."""
        session = await self.get_session(session_id)
        if session:
            return session.add_message(content, role, backend, metadata)
        return None
