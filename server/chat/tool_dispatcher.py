"""
server/chat/tool_dispatcher.py: Despachante e executor de ferramentas do Chief Architect Zeus.
"""

import os
import uuid
from typing import Dict, Any, Optional, Callable

try:
    from state_store import db
except ImportError:
    try:
        from server.state_store import db
    except ImportError:
        db = None

try:
    from git_worktrees import create_slice_worktree
except ImportError:
    try:
        from server.git_worktrees import create_slice_worktree
    except ImportError:
        create_slice_worktree = None

try:
    from test_runner import run_distilled_tests
except ImportError:
    try:
        from server.test_runner import run_distilled_tests
    except ImportError:
        run_distilled_tests = None

try:
    from workers.worker_queue import local_worker_queue
except ImportError:
    try:
        from server.workers.worker_queue import local_worker_queue
    except ImportError:
        local_worker_queue = None

try:
    from server.chat.avatar_telemetry import (
        emit_avatar_state, DISPATCHING_WORKER, TESTING
    )
except ImportError:
    try:
        from chat.avatar_telemetry import (
            emit_avatar_state, DISPATCHING_WORKER, TESTING
        )
    except ImportError:
        emit_avatar_state = None
        DISPATCHING_WORKER = "DISPATCHING_WORKER"
        TESTING = "TESTING"


def dispatch_subagent(
    task_description: str,
    target_slice: str = "",
    isolation_level: str = "worktree",
    repo_root: Optional[str] = None,
    project_id: Optional[str] = None
) -> Dict[str, Any]:
    """Enfileira tarefa de subagente na WorkerQueue e cria Git Worktree isolada se solicitada."""
    slice_id = target_slice.strip() if target_slice and target_slice.strip() else f"slice-{uuid.uuid4().hex[:6]}"
    worktree_res = None

    effective_root = repo_root or (db.get_project_root(project_id) if db and hasattr(db, "get_project_root") else None) or "."

    if isolation_level == "worktree" and create_slice_worktree:
        try:
            worktree_res = create_slice_worktree(slice_id=slice_id, repo_root=effective_root)
        except Exception as e:
            worktree_res = {"status": "ERROR", "error": str(e)}

    ticket_id = None
    if local_worker_queue:
        ticket_id = local_worker_queue.enqueue(
            slice_id=slice_id,
            target_file="workspace",
            instruction_summary=task_description
        )

    return {
        "status": "queued",
        "ticket_id": ticket_id or f"ticket-{uuid.uuid4().hex[:8]}",
        "slice_id": slice_id,
        "isolation_level": isolation_level,
        "worktree": worktree_res,
        "task_description": task_description
    }


def run_test_suite(
    test_target: str = "all",
    run_mode: str = "fast",
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Dispara a suíte de testes do projeto via test_runner de forma determinística."""
    effective_dir = working_dir or (db.get_project_root() if db and hasattr(db, "get_project_root") else None) or "."

    cmd = None
    if test_target and test_target != "all":
        cmd = test_target if test_target.startswith("pytest") else f"pytest {test_target}"

    if run_distilled_tests:
        return run_distilled_tests(
            test_command=cmd,
            working_dir=effective_dir,
            timeout_sec=30 if run_mode == "fast" else 60
        )
    return {"status": "ERROR", "error": "Módulo test_runner não disponível."}


def read_project_status(project_id: Optional[str] = None) -> Dict[str, Any]:
    """Retorna sumário consolidado do projeto ativo (fatias, épico, gates e fila)."""
    target_pid = project_id or (db.get_current_project_id() if db and hasattr(db, "get_current_project_id") else "default")
    state = db.get_state(target_pid) if db and hasattr(db, "get_state") else {}

    slices = state.get("slices", [])
    done = sum(1 for s in slices if str(s.get("status", "")).upper() in ("DONE", "APPROVED", "COMPLETED"))
    in_prog = sum(1 for s in slices if str(s.get("status", "")).upper() in ("IN_PROGRESS", "RUNNING"))
    pending = len(slices) - (done + in_prog)

    slices_summary = {
        "total": len(slices),
        "done": done,
        "in_progress": in_prog,
        "pending": max(0, pending)
    }

    queue_status = local_worker_queue.get_queue_status() if local_worker_queue else None

    return {
        "status": "ok",
        "project_id": target_pid,
        "epic": state.get("epic", {}),
        "slices": slices,
        "slices_summary": slices_summary,
        "gates": state.get("gates", {}),
        "pairs_3x3": state.get("pairs_3x3", []),
        "queue_status": queue_status
    }


def execute_zeus_tool(
    tool_name: str,
    params: Dict[str, Any],
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
    broadcast_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """Executa dinamicamente a ferramenta solicitada e gerencia a telemetria do avatar."""
    sess = session_id or "default"
    norm_name = tool_name.lower()

    if norm_name in ("dispatch_subagent", "subagent_spawn"):
        if emit_avatar_state and broadcast_callback:
            emit_avatar_state(DISPATCHING_WORKER, sess, broadcast_callback, project_id)
        task = params.get("task_description") or params.get("task") or ""
        slice_id = params.get("target_slice") or params.get("slice_id") or ""
        isolation = params.get("isolation_level") or "worktree"
        return dispatch_subagent(task_description=task, target_slice=slice_id, isolation_level=isolation, project_id=project_id)

    elif norm_name == "run_test_suite":
        if emit_avatar_state and broadcast_callback:
            emit_avatar_state(TESTING, sess, broadcast_callback, project_id)
        target = params.get("test_target", "all")
        mode = params.get("run_mode", "fast")
        return run_test_suite(test_target=target, run_mode=mode)

    elif norm_name == "read_project_status":
        pid = params.get("project_id") or project_id
        return read_project_status(project_id=pid)

    return {"status": "ERROR", "error": f"Ferramenta desconhecida: '{tool_name}'"}
