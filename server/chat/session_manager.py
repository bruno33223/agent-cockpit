"""
server/chat/session_manager.py: Gerenciador thread-safe de sessões e mensagens do Zeus Chat.
"""

import time
import uuid
import threading
from typing import Dict, List, Any, Optional, TypedDict


class ChatMessage(TypedDict, total=False):
    """Estrutura representativa de mensagem no histórico do chat."""
    id: str
    role: str
    content: str
    timestamp: float
    thinking: Optional[str]
    tool_calls: Optional[List[Dict[str, Any]]]
    subagents: Optional[List[Dict[str, Any]]]
    images: Optional[List[str]]
    metrics: Optional[Dict[str, Any]]


class SessionManager:
    """Gerenciador thread-safe de sessões e histórico de conversas do Zeus Chat."""

    def __init__(self):
        self._lock = threading.RLock()
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def get_or_create_session(self, session_id: str) -> Dict[str, Any]:
        """Obtém sessão existente ou cria uma nova de forma thread-safe."""
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = {
                    "session_id": session_id,
                    "created_at": time.time(),
                    "updated_at": time.time(),
                    "messages": []
                }
            return self._sessions[session_id]

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Retorna cópia do histórico de mensagens da sessão informada."""
        with self._lock:
            if session_id in self._sessions:
                return list(self._sessions[session_id]["messages"])
            return []

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        thinking: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        subagents: Optional[List[Dict[str, Any]]] = None,
        images: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Adiciona uma nova mensagem estruturada ao histórico da sessão."""
        with self._lock:
            session = self.get_or_create_session(session_id)
            session["updated_at"] = time.time()
            msg_id = str(uuid.uuid4())
            msg: Dict[str, Any] = {
                "id": msg_id,
                "role": role,
                "content": content,
                "timestamp": time.time()
            }
            if thinking:
                msg["thinking"] = thinking
            if tool_calls:
                msg["tool_calls"] = tool_calls
            if subagents:
                msg["subagents"] = subagents
            if images:
                msg["images"] = images
            if metrics:
                msg["metrics"] = metrics

            session["messages"].append(msg)
            return msg

    def clear_session(self, session_id: str) -> bool:
        """Limpa o histórico de mensagens de uma sessão existente."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["messages"] = []
                self._sessions[session_id]["updated_at"] = time.time()
                return True
            return False

    def delete_session(self, session_id: str) -> bool:
        """Remove completamente a sessão da memória."""
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def list_sessions(self) -> List[str]:
        """Retorna os identificadores de todas as sessões ativas."""
        with self._lock:
            return list(self._sessions.keys())
