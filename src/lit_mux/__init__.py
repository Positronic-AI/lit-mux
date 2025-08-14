"""
LIT Mux - Multi-AI multiplexer with REST API

A universal AI backend multiplexer that allows clients to interact with 
multiple AI providers through a unified REST API interface.
"""

__version__ = "0.1.0"
__author__ = "Ben Vierck"
__email__ = "ben@lit.ai"

from .core.session import SessionManager
from .core.router import MessageRouter
from .api.server import LitMuxAPI

__all__ = [
    "SessionManager",
    "MessageRouter", 
    "LitMuxAPI",
]
