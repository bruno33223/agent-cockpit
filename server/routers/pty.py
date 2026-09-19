"""
pty.py: Terminais virtuais PTY multi-sessão, canais WebSocket e gerenciamento de sessões.
"""

import os
import re
import time
import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException

from state_store import db
from fs_utils import _resolve_project_fs_root

try:
    import pty_manager
    pty_session_manager = pty_manager.pty_session_manager
except ImportError:
    try:
        from server import pty_manager
        pty_session_manager = pty_manager.pty_session_manager
    except ImportError:
        pty_session_manager = None

router = APIRouter(tags=["pty"])


@router.websocket("/ws/terminal")
async def websocket_terminal(
    websocket: WebSocket,
    session_id: Optional[str] = Query("term-1"),
    cwd: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    task_id: Optional[str] = Query(None),
    role: Optional[str] = Query("orchestrator"),
    name: Optional[str] = Query(None),
    agent_type: Optional[str] = Query("bash"),
    agent_name: Optional[str] = Query(None),
    slice_id: Optional[str] = Query(None)
):
    target_slice = slice_id or task_id
    if target_slice:
        if ".." in target_slice or "/" in target_slice or "\\" in target_slice or not re.match(r"^[a-zA-Z0-9_\-]+$", target_slice):
            await websocket.close(code=1008)
            return

    target_pid = project_id or db.get_current_project_id()
    root_path, _, _ = _resolve_project_fs_root(target_pid)
    if cwd:
        if not os.path.isabs(cwd):
            real_cwd = os.path.realpath(os.path.join(root_path, cwd))
        else:
            real_cwd = os.path.realpath(cwd)
        real_root = os.path.realpath(root_path)
        try:
            common = os.path.commonpath([real_root, real_cwd])
            if common != real_root:
                await websocket.close(code=1008)
                return
            cwd = real_cwd
        except Exception:
            await websocket.close(code=1008)
            return

    await websocket.accept()

    if not pty_session_manager:
        await websocket.send_text("\r\n[Erro: Suporte PTY indisponível nesta plataforma]\r\n")
        await websocket.close()
        return

    if not cwd:
        if target_slice and root_path:
            worktree_dir = os.path.join(root_path, ".worktrees", target_slice)
            if os.path.isdir(worktree_dir):
                cwd = worktree_dir
        if not cwd:
            cwd = root_path if (root_path and os.path.isdir(root_path)) else os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    session = pty_session_manager.get_or_create(
        session_id=session_id,
        cwd=cwd,
        project_id=target_pid,
        task_id=task_id,
        role=role or "orchestrator",
        name=name,
        agent_type=agent_type or "bash",
        agent_name=agent_name,
        slice_id=slice_id or task_id
    )
    history = session.attach(websocket)
    if history:
        await websocket.send_text(history)

    await session.start_reader_if_needed()

    try:
        while True:
            msg = await websocket.receive_text()
            try:
                payload = json.loads(msg)
                if isinstance(payload, dict) and payload.get("type") == "resize":
                    cols = int(payload.get("cols", 80))
                    rows = int(payload.get("rows", 24))
                    session.resize(cols, rows)
                    continue
                elif isinstance(payload, dict) and "data" in payload:
                    session.write(payload["data"])
                    continue
            except Exception:
                pass
            session.write(msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        session.detach(websocket)


@router.get("/api/terminal/sessions")
def get_terminal_sessions(project_id: Optional[str] = None, task_id: Optional[str] = None, role: Optional[str] = None):
    if pty_session_manager:
        if project_id or task_id or role:
            return [s.to_dict() for s in pty_session_manager.get_sessions_by_context(project_id, task_id, role)]
        return pty_session_manager.list_sessions()
    return []


@router.post("/api/terminal/sessions")
def create_terminal_session(data: Dict[str, Any]):
    if not pty_session_manager:
        raise HTTPException(status_code=503, detail="Suporte PTY indisponível nesta plataforma")

    session_id = data.get("session_id") or f"term-{int(time.time()*1000)}"
    project_id = data.get("project_id") or db.get_current_project_id()
    task_id = data.get("task_id")
    role = data.get("role", "orchestrator")
    name = data.get("name")
    agent_type = data.get("agent_type", "bash")
    agent_name = data.get("agent_name")
    slice_id = data.get("slice_id") or task_id
    cwd = data.get("cwd")

    if slice_id:
        if ".." in slice_id or "/" in slice_id or "\\" in slice_id or not re.match(r"^[a-zA-Z0-9_\-]+$", slice_id):
            raise HTTPException(status_code=403, detail=f"Acesso negado: slice_id inválido ({slice_id})")

    root_path, _, _ = _resolve_project_fs_root(project_id)
    if cwd:
        if not os.path.isabs(cwd):
            real_cwd = os.path.realpath(os.path.join(root_path, cwd))
        else:
            real_cwd = os.path.realpath(cwd)
        real_root = os.path.realpath(root_path)
        try:
            common = os.path.commonpath([real_root, real_cwd])
        except ValueError:
            raise HTTPException(status_code=403, detail=f"Acesso negado: cwd fora dos limites do projeto ({cwd})")
        if common != real_root:
            raise HTTPException(status_code=403, detail=f"Acesso negado: cwd fora dos limites do projeto ({cwd})")
        cwd = real_cwd
    else:
        if slice_id and root_path:
            worktree_dir = os.path.join(root_path, ".worktrees", slice_id)
            if os.path.isdir(worktree_dir):
                cwd = worktree_dir
        if not cwd:
            cwd = root_path if (root_path and os.path.isdir(root_path)) else os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    session = pty_session_manager.get_or_create(
        session_id=session_id, cwd=cwd, project_id=project_id, task_id=task_id,
        role=role, name=name, agent_type=agent_type, agent_name=agent_name, slice_id=slice_id
    )
    return session.to_dict()


@router.delete("/api/terminal/sessions/{session_id}")
def delete_terminal_session(session_id: str):
    if pty_session_manager:
        closed = pty_session_manager.close_session(session_id)
        return {"status": "ok" if closed else "not_found", "closed": closed, "session_id": session_id}
    return {"status": "error", "message": "Suporte PTY indisponível"}
