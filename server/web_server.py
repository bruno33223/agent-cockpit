import os
import sys
import json
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))
from state_store import db

app = FastAPI(title="Agent Cockpit Offline Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.subscriptions: Dict[WebSocket, str] = {}
        self.loop: asyncio.AbstractEventLoop = None

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
        """Chamado pelo StateStore a partir de qualquer thread."""
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
            # Eventos globais (como PROJECTS_UPDATED e PROJECT_SWITCHED) vão para todos
            # Eventos específicos de um projeto vão apenas para quem assina aquele projeto ou se project_id for None
            if project_id is None or event_type in ["PROJECTS_UPDATED", "PROJECT_SWITCHED"] or sub_pid == project_id:
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.append(connection)
        for d in disconnected:
            self.disconnect(d)

manager = ConnectionManager()

# Registra o broadcast no StateStore para eventos automáticos
db.register_listener(manager.broadcast_sync)

async def file_watch_loop():
    """Monitora modificações nos arquivos de estado em states/ e workflow_state.json legado em tempo real.
    Garante que atualizações feitas pelo mcp_server (outro processo) sejam propagadas via WebSocket sem F5.
    """
    last_mtimes: Dict[str, float] = {}
    states_dir = db.states_dir
    legacy_file = db.legacy_file

    while True:
        try:
            # 1. Monitora states/*.json
            if os.path.exists(states_dir):
                for entry in os.scandir(states_dir):
                    if entry.is_file() and entry.name.endswith(".json"):
                        fname = entry.name
                        cur_mtime = entry.stat().st_mtime
                        prev_mtime = last_mtimes.get(fname, 0)
                        
                        if prev_mtime == 0:
                            last_mtimes[fname] = cur_mtime
                        elif cur_mtime > prev_mtime:
                            last_mtimes[fname] = cur_mtime
                            if fname == "projects_index.json":
                                await manager._broadcast("PROJECTS_UPDATED", db.list_projects())
                            else:
                                pid = fname[:-5]  # remove .json
                                state = db.get_state(pid)
                                await manager._broadcast("STATE_FULL", state, project_id=pid)

            # 2. Monitora workflow_state.json legado
            if os.path.exists(legacy_file):
                leg_mtime = os.path.getmtime(legacy_file)
                prev_leg = last_mtimes.get("workflow_state.json", 0)
                if prev_leg == 0:
                    last_mtimes["workflow_state.json"] = leg_mtime
                elif leg_mtime > prev_leg:
                    last_mtimes["workflow_state.json"] = leg_mtime
                    sync_pid = db.sync_from_legacy_if_modified()
                    if sync_pid:
                        await manager._broadcast("PROJECTS_UPDATED", db.list_projects())
                        state = db.get_state(sync_pid)
                        await manager._broadcast("STATE_FULL", state, project_id=sync_pid)
        except Exception:
            pass
        await asyncio.sleep(0.3)

@app.on_event("startup")
async def startup_event():
    manager.loop = asyncio.get_running_loop()
    asyncio.create_task(file_watch_loop())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data_text = await websocket.receive_text()
            try:
                msg = json.loads(data_text)
                action = msg.get("action")
                sub_pid = manager.subscriptions.get(websocket, db.get_current_project_id())
                target_pid = msg.get("project_id") or sub_pid

                if action in ["SUBSCRIBE", "SUBSCRIBE_PROJECT"]:
                    new_pid = msg.get("project_id") or db.get_current_project_id()
                    manager.set_subscription(websocket, new_pid)
                    await websocket.send_text(json.dumps({
                        "event": "STATE_FULL",
                        "payload": db.get_state(new_pid),
                        "project_id": new_pid
                    }, ensure_ascii=False))

                elif action == "USER_STEERING":
                    text = msg.get("text", "")
                    if text.strip():
                        db.add_user_steering(text.strip(), project_id=target_pid)

                elif action == "RESET_STATE":
                    db.reset_state(project_id=target_pid)

                elif action == "APPROVE_GATE":
                    gate = msg.get("gate", "gate_ship_approved")
                    db.approve_gate(gate, "web_user", project_id=target_pid)

                elif action == "GET_STATE":
                    await websocket.send_text(json.dumps({
                        "event": "STATE_FULL",
                        "payload": db.get_state(target_pid),
                        "project_id": target_pid
                    }, ensure_ascii=False))

                elif action == "GET_PROJECTS":
                    await websocket.send_text(json.dumps({
                        "event": "PROJECTS_UPDATED",
                        "payload": db.list_projects(),
                        "current_project_id": db.get_current_project_id()
                    }, ensure_ascii=False))

            except Exception as e:
                print(f"[WebSocket] Erro ao processar mensagem do cliente: {e}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ROTAS DE GERENCIAMENTO DE PROJETOS / WORKSPACES
@app.get("/api/projects")
def get_projects():
    """Retorna lista de todos os workspaces conhecidos com metadados."""
    return {
        "current_project_id": db.get_current_project_id(),
        "projects": db.list_projects()
    }

@app.get("/api/projects/current")
def get_current_project():
    pid = db.get_current_project_id()
    return {"current_project_id": pid, "state": db.get_state(pid)}

class SwitchProjectPayload(BaseModel):
    project_id: str

@app.post("/api/projects/switch")
def post_switch_project(payload: SwitchProjectPayload):
    new_pid = db.switch_current_project(payload.project_id)
    return {
        "status": "ok",
        "current_project_id": new_pid,
        "projects": db.list_projects(),
        "state": db.get_state(new_pid)
    }

@app.delete("/api/projects/{project_id}")
def delete_project_endpoint(project_id: str):
    success = db.delete_project(project_id)
    return {"status": "ok" if success else "error", "projects": db.list_projects()}

@app.get("/api/projects/scan")
@app.post("/api/projects/scan")
def scan_projects():
    """Descobre projetos reais em ~/Projects e atualiza a lista de workspaces."""
    projects = db.scan_local_projects()
    return {
        "status": "ok",
        "current_project_id": db.get_current_project_id(),
        "projects": projects
    }

# ROTAS DE ESTADO
@app.get("/api/state")
def get_state(project_id: Optional[str] = None):
    return db.get_state(project_id)

class SteeringPayload(BaseModel):
    text: str
    project_id: Optional[str] = None

@app.post("/api/steering")
def post_steering(payload: SteeringPayload):
    if not payload.text.strip():
        return {"error": "Texto não pode ser vazio"}
    msg = db.add_user_steering(payload.text.strip(), project_id=payload.project_id)
    return {"status": "ok", "message": msg}

class ResetPayload(BaseModel):
    project_id: Optional[str] = None

@app.post("/api/reset")
def post_reset(payload: Optional[ResetPayload] = None):
    pid = payload.project_id if payload else None
    state = db.reset_state(project_id=pid)
    return {"status": "ok", "state": state}

@app.get("/api/health")
def get_health():
    return {"status": "healthy", "service": "agent-cockpit"}

@app.get("/api/graph")
def get_graph(root: str = None, project_id: Optional[str] = None):
    from code_graph import get_graph_elements_for_ui
    target_root = root
    if not target_root:
        state = db.get_state(project_id)
        target_root = state.get("project_root")
    if not target_root or not os.path.exists(target_root):
        parent = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if os.path.basename(os.path.abspath(".")).lower() == "agent-cockpit" and os.path.exists(parent):
            target_root = parent
        else:
            target_root = "."
    return get_graph_elements_for_ui(target_root)

class ProjectRootPayload(BaseModel):
    path: str
    project_id: Optional[str] = None

@app.post("/api/project_root")
def post_project_root(payload: ProjectRootPayload):
    p = payload.path.strip()
    if not os.path.exists(p):
        return {"status": "error", "message": f"Caminho não encontrado: {p}"}
    saved_p = db.set_project_root(p, project_id=payload.project_id)
    return {"status": "ok", "project_root": saved_p}

@app.get("/api/metrics")
def get_metrics(project_id: Optional[str] = None):
    return db.get_metrics(project_id)

class GateApprovalPayload(BaseModel):
    gate: str = "gate_ship_approved"
    approved_by: str = "user"
    project_id: Optional[str] = None

@app.post("/api/gates/approve")
def post_approve_gate(payload: GateApprovalPayload):
    return db.approve_gate(payload.gate, payload.approved_by, project_id=payload.project_id)

@app.get("/api/handoff")
def get_handoff(root: Optional[str] = None, project_id: Optional[str] = None):
    import workflow_lock
    target_root = root or db.get_project_root(project_id) or "."
    data = workflow_lock.read_latest_handoff(target_root)
    if not data:
        return {"status": "NO_HANDOFF_FOUND", "content": "# Nenhum HANDOFF.md encontrado\nExecute a tool MCP `generate_handoff` na conclusão do Épico."}
    return data

@app.get("/api/vault/note")
def get_vault_note(file: str, root: Optional[str] = None, project_id: Optional[str] = None):
    from code_graph import get_file_vault_note
    target_root = root or db.get_project_root(project_id) or "."
    return get_file_vault_note(target_root, file)

class VaultNotePayload(BaseModel):
    file: str
    content: str
    root: Optional[str] = None
    project_id: Optional[str] = None

@app.post("/api/vault/note")
def post_vault_note(payload: VaultNotePayload):
    from code_graph import save_file_vault_note
    target_root = payload.root or db.get_project_root(payload.project_id) or "."
    return save_file_vault_note(target_root, payload.file, payload.content)

@app.post("/api/vault/sync")
def post_vault_sync(payload: Optional[ProjectRootPayload] = None):
    from code_graph import get_graph_elements_for_ui
    pid = payload.project_id if payload else None
    target_root = (payload and payload.path) or db.get_project_root(pid) or "."
    return get_graph_elements_for_ui(target_root)

class AutostartPayload(BaseModel):
    enabled: bool

@app.get("/api/autostart")
def get_autostart_status():
    from autostart import get_autostart_info
    return get_autostart_info()

@app.post("/api/autostart")
def post_autostart_toggle(payload: AutostartPayload):
    from autostart import enable_autostart, disable_autostart, get_autostart_info
    if payload.enabled:
        success = enable_autostart()
    else:
        success = disable_autostart()
    info = get_autostart_info()
    info["success"] = success
    return info

# Monta arquivos estáticos do dashboard visual
WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))
if os.path.exists(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
