import asyncio
from collections import defaultdict
from typing import DefaultDict, Dict, List

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self.active_connections: DefaultDict[str, List[WebSocket]] = defaultdict(list)
        self.lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self.lock:
            self.active_connections[session_id].append(websocket)

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self.lock:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def send_message(self, session_id: str, message: dict) -> None:
        async with self.lock:
            connections = list(self.active_connections.get(session_id, []))
        for connection in connections:
            await connection.send_json(message)

    async def broadcast(self, message: dict) -> None:
        async with self.lock:
            sessions = list(self.active_connections.values())
        for connections in sessions:
            for connection in connections:
                await connection.send_json(message)
