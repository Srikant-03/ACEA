
import socketio

class SocketManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SocketManager, cls).__new__(cls)
            cls._instance.server: socketio.AsyncServer = None
        return cls._instance

    def set_server(self, server: socketio.AsyncServer):
        self.server = server

    async def emit(self, event: str, data: dict, room: str = None):
        if self.server:
            await self.server.emit(event, data, room=room)
