#!/usr/bin/env python3
"""
Simple terminal client to test lit-mux functionality.
Tests the REST API with ollama backend.
"""

import requests
import time
import json
import sys
from typing import Optional


class LitMuxClient:
    """Simple client for testing lit-mux API."""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.session_id: Optional[str] = None
    
    def health_check(self) -> bool:
        """Check if server is running."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                print("✅ lit-mux server is healthy")
                return True
            else:
                print(f"❌ Server returned {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("❌ Cannot connect to lit-mux server")
            print("   Make sure to start it with: lit-mux start")
            return False
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return False
    
    def list_backends(self):
        """List available backends."""
        try:
            response = requests.get(f"{self.base_url}/backends")
            if response.status_code == 200:
                backends = response.json()
                print("Available backends:")
                for backend in backends:
                    status = "✅" if backend["enabled"] and backend["healthy"] else "❌"
                    print(f"  {status} {backend['name']}")
                return backends
            else:
                print(f"❌ Failed to list backends: {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ Error listing backends: {e}")
            return []
    
    def create_session(self, backends: list = None) -> bool:
        """Create a new session."""
        backends = backends or ["ollama"]
        try:
            response = requests.post(f"{self.base_url}/sessions", json={
                "backends": backends,
                "name": "Terminal Test Session"
            })
            if response.status_code == 200:
                session_data = response.json()
                self.session_id = session_data["id"]
                print(f"✅ Created session: {self.session_id}")
                return True
            else:
                print(f"❌ Failed to create session: {response.json()}")
                return False
        except Exception as e:
            print(f"❌ Error creating session: {e}")
            return False
    
    def send_message(self, message: str, backend: str = None) -> Optional[str]:
        """Send a message and get response."""
        if not self.session_id:
            print("❌ No active session. Create one first.")
            return None
        
        try:
            payload = {"content": message}
            if backend:
                payload["backend"] = backend
            
            print(f"🤖 Sending: {message}")
            response = requests.post(
                f"{self.base_url}/sessions/{self.session_id}/message", 
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                ai_response = data["content"]
                backend_used = data["backend"]
                print(f"🎯 {backend_used}: {ai_response}")
                return ai_response
            else:
                error_msg = response.json().get("detail", "Unknown error")
                print(f"❌ Error: {error_msg}")
                return None
                
        except Exception as e:
            print(f"❌ Error sending message: {e}")
            return None
    
    def list_sessions(self):
        """List all sessions."""
        try:
            response = requests.get(f"{self.base_url}/sessions")
            if response.status_code == 200:
                sessions = response.json()
                print(f"Found {len(sessions)} sessions:")
                for session in sessions:
                    print(f"  📁 {session['name']} ({session['message_count']} messages)")
            else:
                print(f"❌ Failed to list sessions: {response.status_code}")
        except Exception as e:
            print(f"❌ Error listing sessions: {e}")


def main():
    """Test lit-mux functionality."""
    print("🧪 Testing lit-mux with terminal client...")
    
    client = LitMuxClient()
    
    # Health check
    if not client.health_check():
        sys.exit(1)
    
    # List backends
    backends = client.list_backends()
    if not backends:
        print("❌ No backends available")
        sys.exit(1)
    
    # Check if ollama is available
    ollama_available = any(b["name"] == "ollama" and b["enabled"] and b["healthy"] for b in backends)
    if not ollama_available:
        print("⚠️  Ollama backend not available - some tests will be skipped")
        print("   To test with Ollama:")
        print("   1. Install Ollama: https://ollama.ai")
        print("   2. Pull a model: ollama pull llama3.1")
        print("   3. Restart lit-mux")
    
    # Create session
    if not client.create_session():
        sys.exit(1)
    
    # List sessions
    client.list_sessions()
    
    if ollama_available:
        # Test messaging
        print("\n🗣️  Testing messaging...")
        response = client.send_message("Hello! Can you respond with just 'Hello from Ollama'?")
        
        if response:
            print("✅ Messaging test passed!")
            
            # Test follow-up message
            client.send_message("What's 2+2?")
        else:
            print("❌ Messaging test failed")
    else:
        print("⚠️  Skipping messaging tests (Ollama not available)")
    
    print("\n🎉 lit-mux testing complete!")
    print("\nNext steps:")
    print("1. Install Ollama to test AI responses")
    print("2. Add more backends (ChatGPT, Claude Desktop)")
    print("3. Build web interface using the REST API")


if __name__ == "__main__":
    main()
