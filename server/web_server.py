"""
web_server.py: Ponto de entrada modular e enxuto do Agent Cockpit Server.
Instancia FastAPI, middlewares, WebSocket /ws, montagem estática e agrega APIRouters.
Governança Issue #32 (< 200 linhas) e Hardening Issue #38 (Autenticação Local).
"""

import os
import sys
import json
import asyncio
from typing import Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(__file__))

from state_store import db
from connection_manager import manager, ConnectionManager
from port_utils import has_listening_socket, is_port_in_use, create_bound_socket, handle_port_conflict
from fs_utils import _resolve_project_fs_root
from auth import auth_middleware, verify_ws_auth, auth_manager, AuthManager

try:
    import opencode_manager
except ImportError:
    try:
        from server import opencode_manager
    except ImportError:
        opencode_manager = None

from routers import telemetry, settings, omniroute, models, pty, orchestrator, zeus_chat
from routers.telemetry import SwitchProjectPayload, post_switch_project, get_state
from routers.settings import get_customizations_mgr, set_customizations_mgr
from routers.omniroute import get_opencode_credentials
from routers.models import (
    ollama_process_manager, auto_start_ollama_task, _get_local_worker_client,
    get_local_worker_queue, get_local_worker_hf_search, _on_ollama_log
)
from routers.pty import pty_session_manager, create_terminal_session, get_terminal_sessions, delete_terminal_session
from routers.orchestrator import get_fs_tree, read_fs_file

app = FastAPI(title="Agent Cockpit Offline Server")
_watch_task: Optional[asyncio.Task] = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:20128", "http://127.0.0.1:20128", "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(auth_middleware)


@app.middleware("http")
async def add_no_cache_for_static_assets(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/api/auth/status")
async def auth_status_endpoint(request: Request):
    """Endpoint público de verificação de status de autenticação."""
    req = auth_manager.is_auth_required()
    tok = auth_manager.extract_token_from_request(request) if req else None
    return {"auth_required": req, "authenticated": auth_manager.verify_token(tok) if req else True}


async def file_watch_loop():
    last_mtimes: Dict[str, float] = {}
    while True:
        try:
            if os.path.exists(db.states_dir):
                for entry in os.scandir(db.states_dir):
                    if entry.is_file() and entry.name.endswith(".json"):
                        cur_mtime = entry.stat().st_mtime
                        if entry.name not in last_mtimes or cur_mtime > last_mtimes[entry.name]:
                            last_mtimes[entry.name] = cur_mtime
                            if entry.name == "projects_index.json":
                                await manager._broadcast("PROJECTS_UPDATED", db.list_projects())
                            else:
                                pid = entry.name[:-5]
                                await manager._broadcast("STATE_FULL", db.get_state(pid), project_id=pid)
            if os.path.exists(db.legacy_file):
                leg_mtime = os.path.getmtime(db.legacy_file)
                if last_mtimes.get("workflow_state.json", 0) == 0 or leg_mtime > last_mtimes["workflow_state.json"]:
                    last_mtimes["workflow_state.json"] = leg_mtime
                    user_pid = db.get_current_project_id()
                    sync_pid = db.sync_from_legacy_if_modified()
                    if db.get_current_project_id() != user_pid:
                        db.switch_current_project(user_pid)
                    if sync_pid:
                        await manager._broadcast("PROJECTS_UPDATED", db.list_projects())
                        await manager._broadcast("STATE_FULL", db.get_state(sync_pid), project_id=sync_pid)
        except asyncio.CancelledError:
            break
        except Exception:
            pass
        await asyncio.sleep(0.3)


@app.on_event("startup")
async def startup_event():
    global _watch_task
    manager.loop = asyncio.get_running_loop()
    _watch_task = asyncio.create_task(file_watch_loop())
    asyncio.create_task(auto_start_ollama_task())


@app.on_event("shutdown")
async def shutdown_event():
    global _watch_task
    if _watch_task and not _watch_task.done():
        _watch_task.cancel()
    if pty_session_manager:
        try:
            pty_session_manager.stop_all()
        except Exception:
            pass
    ws = sys.modules.get("web_server")
    ollama_mgr = getattr(ws, "ollama_process_manager", ollama_process_manager) if ws else ollama_process_manager
    if ollama_mgr and getattr(ollama_mgr, "managed_by_cockpit", False):
        try:
            res = ollama_mgr.stop()
            if asyncio.iscoroutine(res):
                await res
        except Exception:
            pass
    try:
        from process_lifecycle import get_process_lifecycle_manager
        get_process_lifecycle_manager().shutdown(timeout=2.0)
    except Exception:
        pass


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if not await verify_ws_auth(websocket):
        return
    await manager.connect(websocket)
    try:
        while True:
            msg = json.loads(await websocket.receive_text())
            act = msg.get("action")
            tgt_pid = msg.get("project_id") or manager.subscriptions.get(websocket, db.get_current_project_id())

            if act in ["SUBSCRIBE", "SUBSCRIBE_PROJECT"]:
                new_pid = msg.get("project_id") or db.get_current_project_id()
                manager.set_subscription(websocket, new_pid)
                if msg.get("switch_current", True):
                    db.switch_current_project(new_pid)
                await websocket.send_text(json.dumps({"event": "STATE_FULL", "payload": db.get_state(new_pid), "project_id": new_pid}, ensure_ascii=False))
            elif act == "USER_STEERING" and msg.get("text", "").strip():
                db.add_user_steering(msg["text"].strip(), project_id=tgt_pid, slice_id=msg.get("slice_id"))
            elif act == "RESET_STATE":
                db.reset_state(project_id=tgt_pid)
            elif act == "APPROVE_GATE":
                db.approve_gate(msg.get("gate", "gate_ship_approved"), "web_user", project_id=tgt_pid)
            elif act == "GET_STATE":
                await websocket.send_text(json.dumps({"event": "STATE_FULL", "payload": db.get_state(tgt_pid), "project_id": tgt_pid}, ensure_ascii=False))
            elif act == "GET_PROJECTS":
                await websocket.send_text(json.dumps({"event": "PROJECTS_UPDATED", "payload": db.list_projects(), "current_project_id": db.get_current_project_id()}, ensure_ascii=False))
            elif act == "UPDATE_SETTINGS":
                db.update_settings(msg.get("settings", {}), project_id=tgt_pid)
            elif act == "GET_SETTINGS":
                await websocket.send_text(json.dumps({"event": "SETTINGS_UPDATED", "payload": db.get_settings(tgt_pid), "project_id": tgt_pid}, ensure_ascii=False))
    except (WebSocketDisconnect, Exception):
        manager.disconnect(websocket)


for _r in (telemetry.router, settings.router, omniroute.router, models.router, pty.router, orchestrator.router, zeus_chat.router):
    app.include_router(_r)

# Compatibilidade FastAPI 0.141+ para inspeção direta de app.routes
for inc in list(app.router.routes):
    if hasattr(inc, "original_router"):
        app.router.routes.remove(inc)
        app.router.routes.extend(inc.original_router.routes)

WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))
if os.path.exists(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

for _r in list(app.router.routes):
    if getattr(_r, "name", None) == "web":
        app.router.routes.remove(_r)
        app.router.routes.append(_r)
        break
