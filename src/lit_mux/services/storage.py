"""
Storage service copied from lit-tui.
Handles persistent storage of chat sessions and messages.
"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from uuid import uuid4

import aiofiles


logger = logging.getLogger(__name__)


class ChatMessage:
    """Represents a chat message."""
    
    def __init__(
        self,
        role: str,
        content: str,
        timestamp: Optional[datetime] = None,
        model: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.model = model
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "model": self.model,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatMessage":
        """Create from dictionary."""
        timestamp = datetime.fromisoformat(data["timestamp"])
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=timestamp,
            model=data.get("model"),
            metadata=data.get("metadata", {})
        )


class ChatSession:
    """Represents a chat session."""
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        title: Optional[str] = None,
        created: Optional[datetime] = None,
        updated: Optional[datetime] = None,
        model: Optional[str] = None,
        messages: Optional[List[ChatMessage]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        is_saved: bool = False
    ):
        self.session_id = session_id or str(uuid4())
        self.title = title or f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        self.created = created or datetime.now(timezone.utc)
        self.updated = updated or datetime.now(timezone.utc)
        self.model = model
        self.messages = messages or []
        self.metadata = metadata or {}
        self.is_saved = is_saved
    
    def add_message(self, message: ChatMessage) -> None:
        """Add a message to the session."""
        self.messages.append(message)
        self.updated = datetime.now(timezone.utc)
        
        # Auto-generate title from first user message if not set
        if (self.title.startswith("Chat ") and 
            message.role == "user" and 
            len([m for m in self.messages if m.role == "user"]) == 1):
            self.title = self._generate_title(message.content)
    
    def _generate_title(self, content: str) -> str:
        """Generate a title from message content."""
        # Take first 50 characters and clean up
        title = content.strip()[:50]
        if len(content) > 50:
            title += "..."
        return title
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created": self.created.isoformat(),
            "updated": self.updated.isoformat(),
            "model": self.model,
            "messages": [msg.to_dict() for msg in self.messages],
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatSession":
        """Create from dictionary."""
        created = datetime.fromisoformat(data["created"])
        updated = datetime.fromisoformat(data["updated"])
        messages = [ChatMessage.from_dict(msg_data) for msg_data in data.get("messages", [])]
        
        return cls(
            session_id=data["session_id"],
            title=data["title"],
            created=created,
            updated=updated,
            model=data.get("model"),
            messages=messages,
            metadata=data.get("metadata", {}),
            is_saved=True
        )


class StorageService:
    """Service for managing persistent storage."""
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize storage service."""
        self.storage_dir = storage_dir or Path.home() / ".lit-mux"
        self.sessions_dir = self.storage_dir / "sessions"
        
        # Ensure directories exist
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
    
    async def save_session(self, session: ChatSession) -> None:
        """Save a session to disk."""
        try:
            session_file = self.sessions_dir / f"{session.session_id}.json"
            session_data = session.to_dict()
            
            async with aiofiles.open(session_file, 'w') as f:
                await f.write(json.dumps(session_data, indent=2))
            
            session.is_saved = True
            logger.debug(f"Saved session {session.session_id}")
            
        except Exception as e:
            logger.error(f"Failed to save session {session.session_id}: {e}")
            raise
    
    async def load_session(self, session_id: str) -> Optional[ChatSession]:
        """Load a session from disk."""
        try:
            session_file = self.sessions_dir / f"{session_id}.json"
            
            if not session_file.exists():
                return None
            
            async with aiofiles.open(session_file, 'r') as f:
                session_data = json.loads(await f.read())
            
            return ChatSession.from_dict(session_data)
            
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None
    
    async def list_sessions(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """List available sessions with metadata."""
        try:
            sessions = []
            
            for session_file in self.sessions_dir.glob("*.json"):
                try:
                    async with aiofiles.open(session_file, 'r') as f:
                        session_data = json.loads(await f.read())
                    
                    sessions.append({
                        "session_id": session_data["session_id"],
                        "title": session_data["title"],
                        "created": session_data["created"],
                        "updated": session_data["updated"],
                        "model": session_data.get("model"),
                        "message_count": len(session_data.get("messages", []))
                    })
                    
                except Exception as e:
                    logger.warning(f"Failed to read session file {session_file}: {e}")
                    continue
            
            # Sort by updated time (most recent first)
            sessions.sort(key=lambda x: x["updated"], reverse=True)
            
            if limit:
                sessions = sessions[:limit]
            
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        try:
            session_file = self.sessions_dir / f"{session_id}.json"
            
            if session_file.exists():
                session_file.unlink()
                logger.info(f"Deleted session: {session_id}")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False
