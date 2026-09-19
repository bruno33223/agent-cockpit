"""
server/chat/avatar_telemetry.py: Telemetria e estados visuais do avatar tático via WebSocket/SSE.
"""

import time
from typing import Dict, Any, Optional, Callable, List

IDLE = "IDLE"
LISTENING = "LISTENING"
THINKING = "THINKING"
DISPATCHING_WORKER = "DISPATCHING_WORKER"
TESTING = "TESTING"
SPEAKING = "SPEAKING"

AVATAR_STATES: List[str] = [
    IDLE,
    LISTENING,
    THINKING,
    DISPATCHING_WORKER,
    TESTING,
    SPEAKING
]


def emit_avatar_state(
    state: str,
    session_id: str,
    broadcast_callback: Optional[Callable] = None,
    project_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Emite evento estruturado de estado visual do avatar para WebSocket e SSE."""
    clean_state = state if state in AVATAR_STATES else IDLE
    payload = {
        "type": "avatar_state",
        "state": clean_state,
        "session_id": session_id,
        "timestamp": time.time(),
        **(extra or {})
    }
    if broadcast_callback:
        try:
            broadcast_callback("AVATAR_STATE", payload, project_id)
        except Exception:
            pass
    return payload
