# Socket Manager - Owns the Socket.IO server instance
# This module has NO dependencies on main.py to avoid circular imports

import socketio

# Create the Socket.IO server instance here
# This is THE source of truth for the sio object
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
)

class SocketManager:
    """Singleton for emitting events from anywhere in the app."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SocketManager, cls).__new__(cls)
        return cls._instance

    async def emit(self, event: str, data: dict, room: str = None):
        """Emit an event to connected clients."""
        try:
            await sio.emit(event, data, room=room)
        except Exception as e:
            # Log to console since we can't emit to socket about a socket error
            print(f"Socket Emit Error ({event}): {e}")
