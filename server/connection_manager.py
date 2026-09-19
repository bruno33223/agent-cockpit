"""
connection_manager.py: Gerenciador central de conexões WebSocket e broadcast thread-safe.
"""

import json
import asyncio
from typing import Dict, Optional
from fastapi import WebSocket
from state_store import db


class ConnectionManager:
    def __init__(self):
        self.subscriptions: Dict[WebSocket, str] = {}
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        current_pid = db.get_current_project_id()
        self.subscriptions[websocket] = current_pid

        # Envia lista de projetos disponíveis
        await websocket.send_text(json.dumps({
            "event": "PROJECTS_UPDATED",
            "payload": db.list_projects(),
            "current_project_id": current_pid
        }, ensure_ascii=False))

        # Envia estado inicial completo do projeto ativo ao conectar
        await websocket.send_text(json.dumps({
            "event": "STATE_FULL",
            "payload": db.get_state(current_pid),
            "project_id": current_pid
        }, ensure_ascii=False))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.subscriptions:
            del self.subscriptions[websocket]

    def set_subscription(self, websocket: WebSocket, project_id: str):
        if websocket in self.subscriptions:
            self.subscriptions[websocket] = project_id

    def broadcast_sync(self, event_type: str, payload: dict, project_id: Optional[str] = None):
        """Chamado a partir de qualquer thread de forma síncrona/segura."""
        if self.loop and self.subscriptions:
            asyncio.run_coroutine_threadsafe(
                self._broadcast(event_type, payload, project_id),
                self.loop
            )

    async def _broadcast(self, event_type: str, payload: dict, project_id: Optional[str] = None):
        message = json.dumps({
            "event": event_type,
            "payload": payload,
            "project_id": project_id
        }, ensure_ascii=False)

        disconnected = []
        for connection, sub_pid in list(self.subscriptions.items()):
            if project_id is None or event_type in ["PROJECTS_UPDATED", "PROJECT_SWITCHED"] or sub_pid == project_id:
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.append(connection)
        for d in disconnected:
            self.disconnect(d)


manager = ConnectionManager()
db.register_listener(manager.broadcast_sync)
