"""
WebSocket Manager for Real-time Collaboration
Handles WebSocket connections, message broadcasting, and collaboration state
"""

import json
import uuid
from typing import Dict, List, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Manages WebSocket connections for collaboration sessions"""
    
    def __init__(self):
        # Store active connections by session_id -> connection_id -> websocket
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        # Store user info by connection_id
        self.connection_users: Dict[str, Dict[str, Any]] = {}
        # Store document state by session_id (simple in-memory for now)
        self.document_state: Dict[str, str] = {}
        # Store document revision per session (monotonic)
        self.document_rev: Dict[str, int] = {}
        
    async def connect(self, websocket: WebSocket, session_id: str, user_info: Dict[str, Any]):
        """Connect a new WebSocket and add to session"""
        await websocket.accept()
        
        # Generate unique connection ID
        connection_id = str(uuid.uuid4())
        
        # Initialize session if it doesn't exist
        if session_id not in self.active_connections:
            self.active_connections[session_id] = {}
            
        # Add connection
        self.active_connections[session_id][connection_id] = websocket
        self.connection_users[connection_id] = {
            **user_info,
            'session_id': session_id,
            'connection_id': connection_id,
            'connected_at': asyncio.get_event_loop().time()
        }
        
        # Get current users (excluding the new connection) - deduplicated by user_id
        seen_users = set()
        other_users = []
        for conn_id in self.active_connections[session_id].keys():
            if conn_id in self.connection_users and conn_id != connection_id:
                user_data = self.connection_users[conn_id]
                user_id = user_data.get('user_id')
                if user_id and user_id not in seen_users:
                    seen_users.add(user_id)
                    # Only add most recent connection data for each user
                    other_users.append(user_data)
        
        # Send connection confirmation with current user list
        await self.send_personal_message({
            "type": "connection_established",
            "connection_id": connection_id,
            "session_id": session_id,
            "current_users": len(self.active_connections[session_id]),
            "users": other_users  # Other users in session (excluding self)
        }, websocket)
        logger.debug("Sent connection_established to %s for session %s", connection_id, session_id)
        
        # Send current document state if exists (include rev)
        if session_id in self.document_state:
            await self.send_personal_message({
                "type": "document_state",
                "content": self.document_state[session_id],
                "rev": self.document_rev.get(session_id, 0)
            }, websocket)
        
        # Broadcast user joined with enriched user info (includes connection_id)
        await self.broadcast_to_session(session_id, {
            "type": "user_joined",
            "user": self.connection_users[connection_id],
            "connection_id": connection_id
        }, exclude_connection=connection_id)
        logger.debug("Broadcast user_joined for %s in session %s", connection_id, session_id)
        
        logger.info(f"User {user_info.get('name')} connected to session {session_id}")
        return connection_id
    
    async def disconnect(self, connection_id: str):
        """Disconnect a WebSocket and clean up"""
        if connection_id not in self.connection_users:
            return
            
        user_info = self.connection_users[connection_id]
        session_id = user_info['session_id']
        
        # Remove connection
        if session_id in self.active_connections:
            self.active_connections[session_id].pop(connection_id, None)
            
            # Check if user has any other active connections in this session
            user_id = user_info.get('user_id')
            user_has_other_connections = False
            if user_id:
                for conn_id in self.active_connections[session_id].keys():
                    if conn_id in self.connection_users:
                        if self.connection_users[conn_id].get('user_id') == user_id:
                            user_has_other_connections = True
                            break
            
            # Clean up empty sessions
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
                # Optionally clean up document state after timeout
                
        del self.connection_users[connection_id]
        
        # Only broadcast user left if they have no other active connections
        if session_id in self.active_connections and not user_has_other_connections:
            await self.broadcast_to_session(session_id, {
                "type": "user_left",
                "user": user_info,
                "connection_id": connection_id,
                "user_id": user_info.get('user_id')  # Include user_id for frontend deduplication
            })
            
        logger.info(f"User {user_info.get('name')} disconnected from session {session_id}")
    
    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        """Send message to specific WebSocket"""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
    
    async def broadcast_to_session(self, session_id: str, message: Dict[str, Any], exclude_connection: Optional[str] = None):
        """Broadcast message to all connections in a session concurrently"""
        if session_id not in self.active_connections:
            return
        message['timestamp'] = asyncio.get_event_loop().time()

        async def send_one(connection_id: str, websocket: WebSocket):
            if connection_id == exclude_connection:
                return None
            try:
                await websocket.send_text(json.dumps(message))
                return None
            except Exception as e:
                logger.error(f"Error broadcasting to connection {connection_id}: {e}")
                return connection_id

        tasks = [send_one(cid, ws) for cid, ws in self.active_connections[session_id].items()]
        if not tasks:
            return
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Broadcast gather failed: {e}")
            results = []

        # Clean up failed connections
        for res in results:
            try:
                if isinstance(res, str) and res:
                    await self.disconnect(res)
            except Exception as _e:
                logger.warning(f"Failed to disconnect bad connection {res}: {_e}")
    
    async def handle_document_change(self, session_id: str, connection_id: str, content: str, changes: List[Dict]):
        """Handle document content changes"""
        # Update document state
        self.document_state[session_id] = content
        # Bump revision
        self.document_rev[session_id] = (self.document_rev.get(session_id, 0) + 1)
        current_rev = self.document_rev[session_id]

        # Get user info
        user_info = self.connection_users.get(connection_id, {})
        try:
            logger.info(
                "collab:document_change session=%s rev=%s author=%s len=%s",
                session_id,
                current_rev,
                user_info.get('user_id'),
                len(content or '')
            )
        except Exception:
            pass

        # Broadcast changes to other users
        await self.broadcast_to_session(session_id, {
            "type": "document_changed",
            "content": content,
            "changes": changes,
            "author": user_info.get('name', 'Unknown'),
            "author_id": user_info.get('user_id'),
            "rev": current_rev
        }, exclude_connection=connection_id)
        
    async def handle_cursor_update(self, session_id: str, connection_id: str, cursor_data: Dict):
        """Handle cursor position updates"""
        user_info = self.connection_users.get(connection_id, {})
        
        await self.broadcast_to_session(session_id, {
            "type": "cursor_update",
            "cursor": cursor_data,
            "user": user_info
        }, exclude_connection=connection_id)
    
    def get_session_users(self, session_id: str) -> List[Dict]:
        """Get list of users in a session"""
        if session_id not in self.active_connections:
            return []
            
        return [
            self.connection_users[conn_id] 
            for conn_id in self.active_connections[session_id].keys()
            if conn_id in self.connection_users
        ]

# Global connection manager instance
connection_manager = ConnectionManager()
