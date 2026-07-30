"""WS manager."""
from typing import Dict, Set
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self._connections: Dict[WebSocket, Set[str]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self._connections[websocket] = {"global"}

    def disconnect(self, websocket: WebSocket):
        self._connections.pop(websocket, None)

    async def subscribe(self, websocket: WebSocket, channel: str):
        if websocket in self._connections:
            self._connections[websocket].add(channel)

    async def broadcast(self, message: dict, channel: str = "global"):
        for ws, channels in list(self._connections.items()):
            if channel in channels or "global" in channels:
                try:
                    await ws.send_json(message)
                except:
                    self.disconnect(ws)
