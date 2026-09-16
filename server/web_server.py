import os
import sys
import re
import json
import time
import socket
import asyncio
import threading
import mimetypes
import uuid
import base64
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Body, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    import pty
    import fcntl
    import termios
    import struct
    import signal
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(__file__))
from state_store import db
try:
    import opencode_manager
except ImportError:
    try:
        from server import opencode_manager
    except ImportError:
        opencode_manager = None

try:
    import pty_manager
    pty_session_manager = pty_manager.pty_session_manager
except ImportError:
    try:
        from server import pty_manager
        pty_session_manager = pty_manager.pty_session_manager
    except ImportError:
        pty_session_manager = None

try:
    import zeus_chat_engine
except ImportError:
    try:
        from server import zeus_chat_engine
    except ImportError:
        zeus_chat_engine = None

app = FastAPI(title="Agent Cockpit Offline Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:20128",
        "http://127.0.0.1:20128",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
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

# FILA DO LOCAL WORKER
try:
    from workers.worker_queue import local_worker_queue
except ImportError:
    try:
        from server.workers.worker_queue import local_worker_queue
    except ImportError:
        local_worker_queue = None

if local_worker_queue:
    local_worker_queue.register_listener(
        lambda status: manager.broadcast_sync("worker_queue_updated", status)
    )

# GERENCIADOR DE PROCESSO DO OLLAMA
try:
    from workers.ollama_process_manager import OllamaProcessManager
except ImportError:
    try:
        from server.workers.ollama_process_manager import OllamaProcessManager
    except ImportError:
        OllamaProcessManager = None


if OllamaProcessManager is None:
    import collections
    import shutil
    import subprocess
    import threading

    class _FallbackOllamaProcessManager:
        """Gerenciador de ciclo de vida nativo do Ollama (Fallback / KISS)."""
        def __init__(self, port: int = 11434, max_logs: int = 500, log_callback=None):
            self.port = port
            self.logs = collections.deque(maxlen=max_logs)
            self.log_callback = log_callback
            self.process: Optional[subprocess.Popen] = None
            self.managed_by_cockpit = False
            self._reader_thread = None
            self._lock = threading.Lock()

        def set_log_callback(self, callback):
            self.log_callback = callback

        def is_installed(self) -> bool:
            return shutil.which("ollama") is not None or os.path.exists("/usr/local/bin/ollama")

        def is_port_open(self, port: Optional[int] = None) -> bool:
            p = port or self.port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                return s.connect_ex(("127.0.0.1", p)) == 0

        def start(self, auto_wait: bool = True) -> Dict[str, Any]:
            with self._lock:
                if self.is_port_open():
                    return {
                        "status": "already_running",
                        "running": True,
                        "managed_by_cockpit": self.managed_by_cockpit,
                        "port": self.port,
                        "pid": self.process.pid if self.process else None
                    }

                if not self.is_installed():
                    return {
                        "status": "not_installed",
                        "running": False,
                        "error": "Binário do Ollama não foi encontrado no sistema."
                    }

                ollama_bin = shutil.which("ollama") or "/usr/local/bin/ollama"
                try:
                    self.process = subprocess.Popen(
                        [ollama_bin, "serve"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1
                    )
                    self.managed_by_cockpit = True

                    def _stream_logs():
                        try:
                            for line in iter(self.process.stdout.readline, ""):
                                clean_line = line.rstrip("\r\n")
                                if clean_line:
                                    self.logs.append(clean_line)
                                    if self.log_callback:
                                        try:
                                            self.log_callback(clean_line)
                                        except Exception:
                                            pass
                        except Exception:
                            pass

                    self._reader_thread = threading.Thread(target=_stream_logs, daemon=True)
                    self._reader_thread.start()

                    if auto_wait:
                        for _ in range(30):
                            if self.is_port_open():
                                break
                            time.sleep(0.1)

                    return {
                        "status": "started",
                        "running": self.is_port_open(),
                        "managed_by_cockpit": True,
                        "pid": self.process.pid,
                        "port": self.port
                    }
                except Exception as e:
                    return {
                        "status": "error",
                        "running": False,
                        "error": str(e)
                    }

        def stop(self) -> Dict[str, Any]:
            with self._lock:
                if not self.process:
                    return {
                        "status": "not_running",
                        "running": self.is_port_open(),
                        "managed_by_cockpit": False
                    }

                pid = self.process.pid
                try:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=3.0)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=2.0)
                except Exception as e:
                    return {"status": "error", "error": str(e), "pid": pid}
                finally:
                    self.process = None
                    self.managed_by_cockpit = False

                return {
                    "status": "stopped",
                    "running": False,
                    "managed_by_cockpit": False,
                    "pid": pid
                }

        def get_status(self) -> Dict[str, Any]:
            running = self.is_port_open()
            return {
                "installed": self.is_installed(),
                "running": running,
                "managed_by_cockpit": self.managed_by_cockpit and running,
                "pid": self.process.pid if self.process else None,
                "port": self.port,
                "log_count": len(self.logs)
            }

        def get_logs(self, limit: int = 100) -> List[str]:
            with self._lock:
                logs_list = list(self.logs)
                if limit and limit > 0:
                    return logs_list[-limit:]
                return logs_list

    OllamaProcessManager = _FallbackOllamaProcessManager

def _on_ollama_log(line: str):
    """Callback disparado a cada linha emitida pelo processo Ollama para envio via WebSocket."""
    manager.broadcast_sync("ollama_log", {"line": line})

try:
    ollama_process_manager = OllamaProcessManager(log_callback=_on_ollama_log)
except TypeError:
    ollama_process_manager = OllamaProcessManager()
    if hasattr(ollama_process_manager, "set_log_callback"):
        ollama_process_manager.set_log_callback(_on_ollama_log)
    else:
        ollama_process_manager.log_callback = _on_ollama_log

async def auto_start_ollama_task():
    """Inicialização automática do Ollama em segundo plano se configurado e porta fechada."""
    try:
        cfg = db.get_local_worker_config() if hasattr(db, "get_local_worker_config") else {}
        settings = db.get_settings() if hasattr(db, "get_settings") else {}
        is_local_ai_enabled = bool(cfg.get("enabled", False) or settings.get("enable_local_ai", False))
        auto_start = cfg.get("auto_start_ollama", False) if is_local_ai_enabled else False
        if os.getenv("COCKPIT_NO_OLLAMA") == "1":
            auto_start = False

        if auto_start and ollama_process_manager and ollama_process_manager.is_installed():
            if not ollama_process_manager.is_port_open():
                print("[Ollama] Detectado binário instalado e porta 11434 fechada. Iniciando em background...")
                loop = asyncio.get_running_loop()
                res = await loop.run_in_executor(None, ollama_process_manager.start)
                print(f"[Ollama] Inicialização em background concluída: {res.get('status')}")
                status = ollama_process_manager.get_status()
                manager.broadcast_sync("ollama_status", status)
    except Exception as e:
        print(f"[Ollama] Erro durante inicialização em background: {e}")

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
                    user_active_pid = db.get_current_project_id()
                    sync_pid = db.sync_from_legacy_if_modified()
                    # Blindagem anti-hijacking: impede que arquivos legados ou desconhecidos sobrescrevam current_project_id
                    if db.get_current_project_id() != user_active_pid:
                        db.switch_current_project(user_active_pid)
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
    asyncio.create_task(auto_start_ollama_task())

@app.on_event("shutdown")
async def shutdown_event():
    """Ao encerrar o Cockpit, finaliza sessões PTY ativas e o processo do Ollama se gerenciado."""
    if pty_session_manager:
        try:
            print("[PTY] Encerrando todas as sessões ativas no shutdown...")
            pty_session_manager.stop_all()
        except Exception as e:
            print(f"[PTY] Erro ao encerrar sessões PTY: {e}")

    if ollama_process_manager:
        is_managed = getattr(ollama_process_manager, "managed_by_cockpit", False)
        if is_managed:
            print("[Ollama] Encerrando processo gerenciado pelo Cockpit...")
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, ollama_process_manager.stop)
            except Exception as e:
                print(f"[Ollama] Erro ao encerrar processo: {e}")

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
                    if msg.get("switch_current", True):
                        db.switch_current_project(new_pid)
                    await websocket.send_text(json.dumps({
                        "event": "STATE_FULL",
                        "payload": db.get_state(new_pid),
                        "project_id": new_pid
                    }, ensure_ascii=False))

                elif action == "USER_STEERING":
                    text = msg.get("text", "")
                    slice_id = msg.get("slice_id")
                    if text.strip():
                        db.add_user_steering(text.strip(), project_id=target_pid, slice_id=slice_id)

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

                elif action == "UPDATE_SETTINGS":
                    updates = msg.get("settings", {})
                    db.update_settings(updates, project_id=target_pid)

                elif action == "GET_SETTINGS":
                    await websocket.send_text(json.dumps({
                        "event": "SETTINGS_UPDATED",
                        "payload": db.get_settings(target_pid),
                        "project_id": target_pid
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
    slice_id: Optional[str] = None

@app.post("/api/steering")
def post_steering(payload: SteeringPayload):
    if not payload.text.strip():
        return {"error": "Texto não pode ser vazio"}
    msg = db.add_user_steering(payload.text.strip(), project_id=payload.project_id, slice_id=payload.slice_id)
    return {"status": "ok", "message": msg}

@app.get("/api/steering/messages")
def get_steering_messages(project_id: Optional[str] = None, slice_id: Optional[str] = None):
    messages = db.get_slice_steering_messages(project_id=project_id, slice_id=slice_id)
    return {"status": "ok", "messages": messages, "project_id": project_id, "slice_id": slice_id}

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
    target_pid = project_id or db.get_current_project_id()
    if not target_root:
        root_path, _, _ = _resolve_project_fs_root(target_pid)
        if root_path and os.path.exists(root_path):
            target_root = root_path
        else:
            state = db.get_state(target_pid)
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
    if ".." in file or file.startswith("/") or file.startswith("\\"):
        raise HTTPException(status_code=403, detail="Acesso negado: tentativa de path traversal")
    target_root = root or db.get_project_root(project_id) or "."
    try:
        return get_file_vault_note(target_root, file)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

class VaultNotePayload(BaseModel):
    file: str
    content: str
    root: Optional[str] = None
    project_id: Optional[str] = None

@app.post("/api/vault/note")
def post_vault_note(payload: VaultNotePayload):
    from code_graph import save_file_vault_note
    if ".." in payload.file or payload.file.startswith("/") or payload.file.startswith("\\"):
        raise HTTPException(status_code=403, detail="Acesso negado: tentativa de path traversal")
    target_root = payload.root or db.get_project_root(payload.project_id) or "."
    try:
        return save_file_vault_note(target_root, payload.file, payload.content)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

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

# ROTAS DE CONFIGURAÇÕES GERAIS
class SettingsPayload(BaseModel):
    enable_local_ai: Optional[bool] = None
    delegate_styles_to_cloud: Optional[bool] = None
    model: Optional[str] = None
    auto_start_ollama: Optional[bool] = None
    circuit_breaker_threshold: Optional[int] = None
    project_root: Optional[str] = None
    project_id: Optional[str] = None

@app.get("/api/settings")
def get_settings_endpoint(project_id: Optional[str] = None):
    """Retorna as configurações do Cockpit, incluindo a opção 'DEIXAR ESTILOS COM A NUVEM'."""
    return db.get_settings(project_id=project_id)

@app.post("/api/settings")
def post_settings_endpoint(payload: SettingsPayload):
    """Atualiza configurações do Cockpit e notifica clientes conectados."""
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    updates = {k: v for k, v in data.items() if v is not None and k != "project_id"}
    return db.update_settings(updates, project_id=payload.project_id)

class GovernancePayload(BaseModel):
    autostart_slices: Optional[bool] = None
    security_preset: Optional[str] = None
    human_gate_policy: Optional[str] = None
    artifact_review_policy: Optional[str] = None
    project_id: Optional[str] = None

@app.get("/api/governance")
def get_governance_endpoint(project_id: Optional[str] = None):
    """Retorna as configurações de governança (Autostart de Fatias, Security Preset, Human Gate, Artifact Review)."""
    return db.get_governance_settings(project_id=project_id)

@app.post("/api/governance")
def post_governance_endpoint(payload: GovernancePayload):
    """Atualiza as configurações de governança e notifica clientes conectados."""
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    updates = {k: v for k, v in data.items() if v is not None and k != "project_id"}
    res = db.update_governance_settings(updates, project_id=payload.project_id)
    manager.broadcast_sync("GOVERNANCE_SETTINGS_UPDATED", res)
    return res

# ROTAS DO LOCAL WORKER (Fatia 3)
try:
    from workers.local_llm_client import LocalLLMClient
except ImportError:
    try:
        from server.workers.local_llm_client import LocalLLMClient
    except ImportError:
        LocalLLMClient = None

def _get_local_worker_client(project_id: Optional[str] = None):
    cfg = {}
    if hasattr(db, "get_local_worker_config"):
        cfg = db.get_local_worker_config(project_id)
    else:
        state = db.get_state(project_id)
        cfg = state.get("local_worker", {
            "provider": "ollama",
            "endpoint": "http://127.0.0.1:11434",
            "model": "qwen2.5-coder:7b-instruct-q4_k_m",
            "circuit_breaker_threshold": 2,
            "consecutive_failures": {}
        })
    endpoint = cfg.get("endpoint", "http://127.0.0.1:11434")
    if LocalLLMClient:
        return LocalLLMClient(base_url=endpoint), cfg

    class _FallbackLocalLLMClient:
        RECOMMENDED_MODELS = [
            "deepseek-coder-v2:16b-q3_k_m",
            "deepseek-coder-v2:16b",
            "qwen2.5-coder:7b",
            "qwen2.5-coder:1.5b",
            "deepseek-coder:6.7b",
            "codellama:7b",
            "llama3.2:3b",
        ]
        def __init__(self, base_url="http://127.0.0.1:11434", timeout=5.0):
            self.base_url = base_url.rstrip("/")
            self.timeout = timeout

        def healthcheck(self) -> bool:
            import urllib.request
            try:
                req = urllib.request.Request(f"{self.base_url}/api/tags")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.getcode() == 200
            except Exception:
                return False

        def list_models(self) -> Dict[str, Any]:
            import urllib.request
            try:
                req = urllib.request.Request(f"{self.base_url}/api/tags")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    installed = [m.get("name", "") for m in data.get("models", []) if "name" in m]
                    return {"online": True, "installed": installed, "recommended": list(self.RECOMMENDED_MODELS)}
            except Exception:
                return {"online": False, "installed": [], "recommended": list(self.RECOMMENDED_MODELS)}

        def pull_model(self, model_name: str, stream: bool = False) -> Dict[str, Any]:
            import urllib.request
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/api/pull",
                    data=json.dumps({"name": model_name, "stream": stream}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                return {"status": "error", "message": str(e)}

    return _FallbackLocalLLMClient(base_url=endpoint), cfg

@app.get("/api/local-worker/queue")
def get_local_worker_queue(slice_id: Optional[str] = None, ticket_id: Optional[str] = None):
    """Retorna o status atual da fila de tarefas da GPU do Local Worker lendo snapshot compartilhado."""
    if local_worker_queue:
        return local_worker_queue.get_queue_status(slice_id=slice_id, ticket_id=ticket_id)
    try:
        from workers.worker_queue import DEFAULT_SNAPSHOT_PATH
        if os.path.exists(DEFAULT_SNAPSHOT_PATH):
            with open(DEFAULT_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "is_busy": False,
        "active_task": None,
        "queue_length": 0,
        "queued_tasks": [],
        "your_position": None,
        "message": "Fila do Local Worker não inicializada."
    }

@app.get("/api/local-worker/status")
def get_local_worker_status(project_id: Optional[str] = None):
    client, cfg = _get_local_worker_client(project_id)
    online = client.healthcheck()
    res = {
        "status": "ok",
        "online": online,
        "provider": cfg.get("provider", "ollama"),
        "endpoint": cfg.get("endpoint", "http://127.0.0.1:11434"),
        "model": cfg.get("model", "qwen2.5-coder:7b-instruct-q4_k_m"),
        "circuit_breaker_threshold": cfg.get("circuit_breaker_threshold", 2),
        "consecutive_failures": cfg.get("consecutive_failures", {}),
        "auto_start_ollama": cfg.get("auto_start_ollama", True),
        "delegate_styles_to_cloud": cfg.get("delegate_styles_to_cloud", False)
    }
    if ollama_process_manager:
        res["server_status"] = ollama_process_manager.get_status()
    return res

@app.post("/api/local-worker/start-server")
def post_local_worker_start_server():
    """Inicia o processo local do Ollama."""
    if not ollama_process_manager:
        return {"status": "ERROR", "error": "OllamaProcessManager não está disponível.", "installed": False}
    try:
        res = ollama_process_manager.start()
        status = ollama_process_manager.get_status()
        manager.broadcast_sync("ollama_status", status)
        return res
    except (RuntimeError, Exception) as e:
        status = ollama_process_manager.get_status() if ollama_process_manager else {"installed": False, "running": False}
        manager.broadcast_sync("ollama_status", status)
        return {"status": "ERROR", "error": str(e), "installed": False}

@app.post("/api/local-worker/stop-server")
def post_local_worker_stop_server():
    """Encerra o processo local do Ollama caso tenha sido iniciado pelo Cockpit."""
    if not ollama_process_manager:
        return {"status": "ERROR", "error": "OllamaProcessManager não está disponível.", "installed": False}
    try:
        res = ollama_process_manager.stop()
        status = ollama_process_manager.get_status()
        manager.broadcast_sync("ollama_status", status)
        return res
    except (RuntimeError, Exception) as e:
        status = ollama_process_manager.get_status() if ollama_process_manager else {"installed": False, "running": False}
        manager.broadcast_sync("ollama_status", status)
        return {"status": "ERROR", "error": str(e), "installed": status.get("installed", False)}

@app.get("/api/local-worker/server-logs")
def get_local_worker_server_logs(limit: int = 100):
    """Retorna os logs recentes do servidor Ollama."""
    if not ollama_process_manager:
        return {"status": "unavailable", "logs": [], "count": 0}
    logs = ollama_process_manager.get_logs(limit=limit)
    status = ollama_process_manager.get_status()
    return {
        "status": "ok",
        "logs": logs,
        "count": len(logs),
        "running": status.get("running", False),
        "managed_by_cockpit": status.get("managed_by_cockpit", False),
        "installed": status.get("installed", False)
    }

@app.get("/api/local-worker/models")
def get_local_worker_models(project_id: Optional[str] = None):
    client, cfg = _get_local_worker_client(project_id)
    models_info = client.list_models()
    return {
        "status": "ok",
        "online": models_info.get("online", False),
        "installed": models_info.get("installed", []),
        "recommended": models_info.get("recommended", []),
        "current_model": cfg.get("model", "qwen2.5-coder:7b-instruct-q4_k_m")
    }

class LocalWorkerSelectPayload(BaseModel):
    model: str
    project_id: Optional[str] = None

@app.post("/api/local-worker/select")
def post_local_worker_select(payload: LocalWorkerSelectPayload):
    model_name = payload.model.strip()
    if not model_name:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Nome do modelo não pode ser vazio.")

    if hasattr(db, "set_local_worker_config"):
        cfg = db.set_local_worker_config({"model": model_name}, project_id=payload.project_id)
    else:
        target_pid = db.resolve_project_id(payload.project_id)
        with db.lock:
            state = db.get_state(target_pid)
            cfg = state.setdefault("local_worker", {
                "provider": "ollama",
                "endpoint": "http://127.0.0.1:11434",
                "model": "qwen2.5-coder:7b-instruct-q4_k_m",
                "circuit_breaker_threshold": 2,
                "consecutive_failures": {}
            })
            cfg["model"] = model_name
            db._save_state(state, target_pid)
        db._notify("LOCAL_WORKER_CONFIG_UPDATED", cfg, target_pid)
        db._notify("STATE_FULL", state, target_pid)

    return {
        "status": "ok",
        "model": model_name,
        "config": cfg
    }

class LocalWorkerPullPayload(BaseModel):
    model: str
    project_id: Optional[str] = None

@app.post("/api/local-worker/pull")
def post_local_worker_pull(payload: LocalWorkerPullPayload):
    model_name = payload.model.strip()
    if not model_name:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Nome do modelo não pode ser vazio.")

    client, _ = _get_local_worker_client(payload.project_id)

    def _bg_pull():
        def on_progress(chunk: dict):
            manager.broadcast_sync("model_pull_progress", {"model": model_name, "progress": chunk})

        try:
            res = client.pull_model(model_name, stream=True, progress_callback=on_progress)
            if isinstance(res, dict) and (res.get("status") == "error" or "error" in res):
                err_msg = res.get("message") or res.get("error") or "Falha ao baixar modelo"
                manager.broadcast_sync("model_pull_complete", {"model": model_name, "status": "error", "message": err_msg})
            else:
                manager.broadcast_sync("model_pull_complete", {"model": model_name, "status": "success"})
        except Exception as e:
            manager.broadcast_sync("model_pull_complete", {"model": model_name, "status": "error", "message": str(e)})

    thread = threading.Thread(target=_bg_pull, daemon=True)
    thread.start()

    return {
        "status": "pulling",
        "model": model_name,
        "message": f"Download de '{model_name}' iniciado em segundo plano no Ollama. Acompanhe o progresso no Console de Logs."
    }

try:
    from workers.hf_hub_client import HFHubClient
except ImportError:
    try:
        from server.workers.hf_hub_client import HFHubClient
    except ImportError:
        HFHubClient = None

@app.get("/api/local-worker/hf-search")
def get_local_worker_hf_search(query: str = "", limit: int = 20):
    """Busca modelos GGUF no Hugging Face Hub para instalacao no Ollama / Local Worker."""
    if HFHubClient:
        client = HFHubClient()
        results = client.search_models(query=query, limit=limit)
    else:
        results = []
    return {
        "query": query,
        "count": len(results),
        "models": results
    }

# =========================================================================
# ROTAS DE INTEGRAÇÃO: OMNIROUTE & OPENCODE
# =========================================================================

class OmniRouteConfigPayload(BaseModel):
    omniroute_url: Optional[str] = "http://localhost:20128/v1"
    api_key: Optional[str] = "omniroute-local"
    model: Optional[str] = "auto"
    enabled: Optional[bool] = True

@app.get("/api/omniroute/status")
def get_omniroute_status(base_url: Optional[str] = None):
    """Testa a conectividade com o OmniRoute e recupera a lista de modelos."""
    if opencode_manager:
        return opencode_manager.check_omniroute_health(base_url)
    return {"online": False, "models": [], "message": "Módulo opencode_manager não disponível"}

@app.get("/api/omniroute/config")
def get_omniroute_config():
    """Retorna as configurações salvas de OmniRoute e OpenCode."""
    if opencode_manager:
        return opencode_manager.load_config()
    return {"omniroute_url": "http://localhost:20128/v1", "api_key": "omniroute-local", "model": "auto"}

@app.post("/api/omniroute/config")
def post_omniroute_config(payload: OmniRouteConfigPayload):
    """Salva configurações de OmniRoute e sincroniza opencode.json."""
    if opencode_manager:
        data = payload.dict(exclude_unset=True)
        res = opencode_manager.save_config(data)
        manager.broadcast_sync("OMNIROUTE_CONFIG_UPDATED", res)
        return {"status": "success", "config": res}
    return {"status": "error", "message": "Módulo opencode_manager não disponível"}

@app.get("/api/opencode/binaries")
def get_opencode_binaries():
    """Verifica a presença dos binários de opencode, omniroute, node e npm."""
    if opencode_manager:
        return opencode_manager.detect_binaries()
    return {"opencode": {"installed": False}, "omniroute": {"installed": False}}

@app.post("/api/opencode/sync-config")
def post_opencode_sync():
    """Gera/sincroniza o arquivo opencode.json na raiz do projeto com MCP do Cockpit."""
    if opencode_manager:
        return opencode_manager.sync_opencode_config()
    return {"status": "error", "message": "Módulo opencode_manager não disponível"}

@app.get("/api/omniroute/connectors")
def get_omniroute_connectors(base_url: Optional[str] = None):
    """Retorna os conectores e provedores detectados no OmniRoute."""
    if opencode_manager:
        connectors = opencode_manager.detect_omniroute_connectors(base_url)
        return {
            "online": True if connectors else False,
            "connectors": connectors,
            "count": len(connectors)
        }
    return {"online": False, "connectors": [], "count": 0, "message": "Módulo opencode_manager não disponível"}

@app.get("/api/opencode/credentials")
def get_opencode_credentials():
    """Retorna as credenciais e configurações detectadas do OpenCode."""
    if opencode_manager:
        return opencode_manager.detect_opencode_credentials()
    return {"omniroute_url": None, "api_key": None, "model": None, "sources": []}

@app.get("/api/opencode/detect")
def get_opencode_detect():
    """Detecta credenciais e configurações do OpenCode para auto-preenchimento do frontend."""
    creds = get_opencode_credentials()
    return {"status": "ok", "credentials": creds}


# =========================================================================
# OPENCODE HEADLESS REST ENDPOINTS & SUBAGENT TRACKING
# =========================================================================

@app.post("/api/opencode/headless/start")
def post_opencode_headless_start(req: Optional[Dict[str, Any]] = Body(default={})):
    """Inicia uma sessão headless do OpenCode em segundo plano sem bloquear threads."""
    req_data = req or {}
    session_id = req_data.get("session_id")
    prompt = req_data.get("prompt")
    cwd = req_data.get("cwd")
    model = req_data.get("model")
    project_id = req_data.get("project_id") or db.get_current_project_id()

    if opencode_manager:
        res = opencode_manager.start_headless_session(
            session_id=session_id,
            prompt=prompt,
            cwd=cwd,
            model=model,
            project_id=project_id,
            broadcast_callback=manager.broadcast_sync
        )
        return {
            "status": "ok",
            "session_id": res.get("session_id"),
            "running": res.get("running", True),
            "data": res
        }
    return {"status": "error", "message": "Módulo opencode_manager não disponível"}


@app.post("/api/opencode/headless/message")
def post_opencode_headless_message(req: Dict[str, Any] = Body(...)):
    """Envia uma mensagem do usuário para a sessão headless e emite OPENCODE_CHAT_MESSAGE."""
    session_id = req.get("session_id")
    message = req.get("message", "")
    if not session_id:
        return {"status": "error", "message": "session_id é obrigatório"}

    if opencode_manager:
        res = opencode_manager.send_headless_message(
            session_id=session_id,
            message=message,
            broadcast_callback=manager.broadcast_sync
        )
        return {
            "status": "ok",
            "session_id": session_id,
            "message": message,
            "data": res
        }
    return {"status": "error", "message": "Módulo opencode_manager não disponível"}


@app.get("/api/opencode/headless/subagents")
def get_opencode_headless_subagents(session_id: Optional[str] = None):
    """Lista subagentes ativos e suas respectivas sessões de terminal e stream."""
    if opencode_manager:
        subagents = opencode_manager.list_subagents(parent_session_id=session_id)
        return {
            "status": "ok",
            "subagents": subagents,
            "count": len(subagents)
        }
    return {"status": "error", "subagents": [], "count": 0, "message": "Módulo opencode_manager não disponível"}


@app.post("/api/opencode/headless/subagents")
def post_opencode_headless_subagents(req: Dict[str, Any] = Body(...)):
    """Registra dinamicamente um subagente e emite evento WebSocket SUBAGENT_SPAWNED."""
    if opencode_manager:
        subagent = opencode_manager.register_subagent(
            parent_session_id=req.get("parent_session_id", req.get("session_id", "default")),
            subagent_id=req.get("subagent_id", req.get("id")),
            role=req.get("role", "builder"),
            task=req.get("task", ""),
            terminal_id=req.get("terminal_id"),
            stream_id=req.get("stream_id"),
            meta=req.get("meta"),
            broadcast_callback=manager.broadcast_sync
        )
        return {"status": "ok", "subagent": subagent}
    return {"status": "error", "message": "Módulo opencode_manager não disponível"}


@app.get("/api/opencode/headless/status")
def get_opencode_headless_status(session_id: Optional[str] = None):
    """Retorna o status atual da sessão headless ou estatísticas de sessões ativas."""
    if opencode_manager:
        status_info = opencode_manager.get_headless_status(session_id)
        return {"status": "ok", "data": status_info}
    return {"status": "error", "message": "Módulo opencode_manager não disponível"}



# =========================================================================
# WEBSOCKET: TERMINAL PTY MULTI-SESSÃO (XTERM.JS RUNNER / ALETHE STYLE)
# =========================================================================

@app.websocket("/ws/terminal")
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

    # Determina diretório de trabalho do projeto ativo se não fornecido
    if not cwd:
        if target_slice and root_path:
            worktree_dir = os.path.join(root_path, ".worktrees", target_slice)
            if os.path.isdir(worktree_dir):
                cwd = worktree_dir
        if not cwd:
            cwd = root_path if (root_path and os.path.isdir(root_path)) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

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

@app.get("/api/terminal/sessions")
def get_terminal_sessions(project_id: Optional[str] = None, task_id: Optional[str] = None, role: Optional[str] = None):
    """Lista as sessões ativas e persistidas de terminal PTY com PID, CWD, papel (role) e status."""
    if pty_session_manager:
        if project_id or task_id or role:
            return [s.to_dict() for s in pty_session_manager.get_sessions_by_context(project_id, task_id, role)]
        return pty_session_manager.list_sessions()
    return []

@app.post("/api/terminal/sessions")
def create_terminal_session(data: Dict[str, Any]):
    """Cria ou registra programaticamente uma sessão de terminal especializada com persistência em disco."""
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

    # Validação de segurança: slice_id
    if slice_id:
        if ".." in slice_id or "/" in slice_id or "\\" in slice_id or not re.match(r"^[a-zA-Z0-9_\-]+$", slice_id):
            raise HTTPException(status_code=403, detail=f"Acesso negado: slice_id inválido ou tentativa de path traversal ({slice_id})")

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
            cwd = root_path if (root_path and os.path.isdir(root_path)) else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    session = pty_session_manager.get_or_create(
        session_id=session_id,
        cwd=cwd,
        project_id=project_id,
        task_id=task_id,
        role=role,
        name=name,
        agent_type=agent_type,
        agent_name=agent_name,
        slice_id=slice_id
    )
    return session.to_dict()

@app.delete("/api/terminal/sessions/{session_id}")
def delete_terminal_session(session_id: str):
    """Encerra um terminal PTY específico de forma limpa e remove da persistência."""
    if pty_session_manager:
        closed = pty_session_manager.close_session(session_id)
        return {"status": "ok" if closed else "not_found", "closed": closed, "session_id": session_id}
    return {"status": "error", "message": "Suporte PTY indisponível"}


# ROTAS DO FILE EXPLORER (ORCA RIGHT SIDEBAR)
DEFAULT_FS_IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "dist", "build", ".next", ".nuxt",
    ".output", ".turbo", ".cache", ".idea", ".vscode"
}
DEFAULT_FS_IGNORE_FILES = {
    ".git", ".DS_Store", "Thumbs.db", ".env", ".env.local"
}

def _resolve_project_fs_root(project_id: Optional[str] = None) -> tuple:
    """Resolve o caminho raiz físico, nome e ID canônico do projeto especificado ou atual."""
    base_cockpit_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if not project_id:
        return base_cockpit_dir, "Agent Cockpit", "default"

    target_pid = db.resolve_project_id(project_id)
    root_path = db.get_project_root(target_pid)
    
    project_name = None
    if not root_path or not os.path.exists(root_path):
        index_data = db._read_index()
        proj_meta = index_data.get("projects", {}).get(target_pid, {})
        idx_root = proj_meta.get("project_root")
        if idx_root and os.path.exists(idx_root):
            root_path = idx_root
        project_name = proj_meta.get("name")
    
    if not root_path or not os.path.exists(root_path):
        root_path = base_cockpit_dir

    root_path = os.path.abspath(root_path)
    if not project_name:
        state = db.get_state(target_pid)
        project_name = state.get("epic", {}).get("name") or os.path.basename(root_path) or "Projeto"
        
    return root_path, project_name, target_pid

@app.get("/api/fs/tree")
def get_fs_tree(
    project_id: Optional[str] = None,
    subpath: Optional[str] = "",
    max_depth: int = 4
):
    """
    Retorna a árvore hierárquica de arquivos e pastas do projeto em formato JSON:
    {"root": "/path", "name": "project_name", "project_id": "...", "entries": [...]}
    """
    if not isinstance(project_id, str):
        project_id = None
    if not isinstance(subpath, str):
        subpath = ""
    if not isinstance(max_depth, int):
        max_depth = 4

    root_path, project_name, target_pid = _resolve_project_fs_root(project_id)
    
    clean_subpath = os.path.normpath((subpath or "").strip().lstrip("/\\"))
    if clean_subpath and clean_subpath != ".":
        target_dir = os.path.abspath(os.path.join(root_path, clean_subpath))
        try:
            if os.path.commonpath([root_path, target_dir]) != root_path:
                raise HTTPException(status_code=403, detail="Acesso negado: subcaminho fora da raiz do projeto.")
        except ValueError:
            raise HTTPException(status_code=403, detail="Acesso negado: unidade diferente ou caminho inválido.")
    else:
        target_dir = root_path
        clean_subpath = ""

    if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
        raise HTTPException(status_code=404, detail="Diretório não encontrado.")

    def _build_tree(curr_dir: str, rel_prefix: str, current_depth: int) -> List[Dict[str, Any]]:
        if current_depth > max_depth:
            return []
        
        try:
            with os.scandir(curr_dir) as it:
                items = list(it)
        except (PermissionError, OSError):
            return []

        dirs = []
        files = []
        for entry in items:
            name = entry.name
            if (
                name in DEFAULT_FS_IGNORE_DIRS
                or name in DEFAULT_FS_IGNORE_FILES
                or name.startswith(".env")
                or name == ".git"
            ):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    dirs.append(entry)
                elif entry.is_file(follow_symlinks=False):
                    files.append(entry)
            except OSError:
                continue

        dirs.sort(key=lambda x: x.name.lower())
        files.sort(key=lambda x: x.name.lower())

        result = []
        for d in dirs:
            child_rel = os.path.join(rel_prefix, d.name) if rel_prefix else d.name
            child_rel_norm = child_rel.replace("\\", "/")
            children = []
            if current_depth < max_depth:
                children = _build_tree(d.path, child_rel_norm, current_depth + 1)
            result.append({
                "name": d.name,
                "path": child_rel_norm,
                "type": "directory",
                "children": children
            })

        for f in files:
            child_rel = os.path.join(rel_prefix, f.name) if rel_prefix else f.name
            child_rel_norm = child_rel.replace("\\", "/")
            try:
                size = f.stat().st_size
            except OSError:
                size = 0
            result.append({
                "name": f.name,
                "path": child_rel_norm,
                "type": "file",
                "size": size
            })

        return result

    entries = _build_tree(target_dir, clean_subpath.replace("\\", "/"), 1)
    
    return {
        "root": root_path,
        "name": project_name,
        "project_id": target_pid,
        "subpath": clean_subpath.replace("\\", "/"),
        "entries": entries
    }

@app.get("/api/fs/read")
def read_fs_file(
    path: str,
    project_id: Optional[str] = None,
    max_bytes: int = 512 * 1024
):
    """
    Retorna o conteúdo do arquivo em texto seguro para visualização ou preview rápido.
    """
    if not isinstance(project_id, str):
        project_id = None
    if not isinstance(max_bytes, int):
        max_bytes = 512 * 1024

    root_path, project_name, target_pid = _resolve_project_fs_root(project_id)
    
    clean_p = (path or "").strip()
    if not clean_p:
        raise HTTPException(status_code=400, detail="Parâmetro 'path' é obrigatório.")
    if os.path.isabs(clean_p):
        target_file = os.path.abspath(clean_p)
        allowed_roots = [root_path]
        for p in db.list_projects():
            pr = p.get("project_root")
            if pr and os.path.exists(pr):
                allowed_roots.append(os.path.abspath(pr))
        
        is_safe = False
        for r in allowed_roots:
            try:
                if os.path.commonpath([r, target_file]) == r:
                    is_safe = True
                    break
            except ValueError:
                continue
        if not is_safe:
            raise HTTPException(status_code=403, detail="Acesso negado fora do espaço do projeto.")
    else:
        norm_p = os.path.normpath(clean_p.lstrip("/\\"))
        target_file = os.path.abspath(os.path.join(root_path, norm_p))
        try:
            if os.path.commonpath([root_path, target_file]) != root_path:
                raise HTTPException(status_code=403, detail="Acesso negado: tentativa de escape da raiz.")
        except ValueError:
            raise HTTPException(status_code=403, detail="Caminho inválido.")

    if not os.path.exists(target_file):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    file_name = os.path.basename(target_file)
    if (
        file_name in DEFAULT_FS_IGNORE_FILES
        or file_name in DEFAULT_FS_IGNORE_DIRS
        or file_name.startswith(".env")
        or file_name == ".git"
    ):
        raise HTTPException(status_code=403, detail="Acesso negado: arquivo ou recurso restrito.")

    if not os.path.isfile(target_file):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    try:
        rel_path = os.path.relpath(target_file, root_path).replace("\\", "/")
    except ValueError:
        rel_path = file_name

    file_size = os.path.getsize(target_file)
    
    mime_type, _ = mimetypes.guess_type(target_file)
    mime_type = mime_type or "text/plain"

    try:
        with open(target_file, "rb") as f:
            chunk = f.read(max_bytes)
        
        if b"\x00" in chunk[:8192]:
            return {
                "path": rel_path,
                "name": file_name,
                "size": file_size,
                "is_binary": True,
                "content": "",
                "truncated": False,
                "mime": mime_type,
                "error": "Arquivo binário não suportado para visualização em texto."
            }

        try:
            text_content = chunk.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text_content = chunk.decode("latin-1")
            except Exception:
                return {
                    "path": rel_path,
                    "name": file_name,
                    "size": file_size,
                    "is_binary": True,
                    "content": "",
                    "truncated": False,
                    "mime": mime_type,
                    "error": "Codificação de arquivo não suportada para preview de texto."
                }

        return {
            "path": rel_path,
            "name": file_name,
            "size": file_size,
            "is_binary": False,
            "content": text_content,
            "truncated": file_size > max_bytes,
            "mime": mime_type
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler arquivo: {str(e)}")

# Monta arquivos estáticos do dashboard visual
WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))
if os.path.exists(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

# =========================================================================
# UTILITÁRIOS DE VERIFICAÇÃO DE PORTA E CONFLITO (NATIVE SOCKET BIND)
# =========================================================================

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """
    Verifica se a porta está em uso utilizando bind nativo via socket com SO_REUSEADDR.
    Retorna True se a porta estiver ocupada / em uso, ou False se estiver livre para bind.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return False
        except (OSError, socket.error):
            return True

def handle_port_conflict(port: int = 8765, host: str = "127.0.0.1", force: bool = False) -> bool:
    """
    Verifica se a porta está ocupada de forma robusta e segura.
    - Utiliza verificação nativa de socket bind (SO_REUSEADDR) em Python,
      sem confiar cegamente em saída de lsof ou falhas de permissão.
    - Se for o próprio Agent Cockpit (instância zumbi/anterior): encerra e libera a porta.
    - Se for processo alheio: não encerra (a menos que force=True) e reporta aviso.
    - Antes de declarar a porta como livre, valida via socket bind nativo.
    Retorna True se a porta está livre para uso, False caso contrário.
    """
    import subprocess

    # Verificação inicial: se socket bind tem sucesso imediato, porta livre!
    if not is_port_in_use(port=port, host=host):
        return True

    # A porta está ocupada. Tenta inspecionar processos em escuta
    current_pid = os.getpid()
    listening_pids = set()

    if sys.platform == "win32":
        try:
            out = subprocess.check_output(f'netstat -ano | findstr :{port}', shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in out.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in parts:
                    try:
                        p = int(parts[-1])
                        if p != current_pid:
                            listening_pids.add(p)
                    except ValueError:
                        pass
        except Exception:
            pass
    else:
        try:
            out = subprocess.check_output(f"lsof -ti :{port}", shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in out.strip().splitlines():
                try:
                    p = int(line)
                    if p != current_pid:
                        listening_pids.add(p)
                except ValueError:
                    pass
        except Exception:
            pass

    def _inspect_process(pid: int):
        name = "desconhecido"
        cmdline = ""
        if sys.platform == "win32":
            try:
                tl = subprocess.check_output(f'tasklist /FI "PID eq {pid}" /FO CSV /NH', shell=True, text=True, stderr=subprocess.DEVNULL)
                for line in tl.strip().splitlines():
                    if line.startswith('"'):
                        name = line.split('"')[1]
                        break
            except Exception:
                pass
            try:
                ps_cmd = f'powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object ProcessId -eq {pid}).CommandLine"'
                cmdline = subprocess.check_output(ps_cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            except Exception:
                pass
        else:
            try:
                p_out = subprocess.check_output(["ps", "-p", str(pid), "-o", "comm=,args="], text=True, stderr=subprocess.DEVNULL).strip()
                if p_out:
                    parts = p_out.split(None, 1)
                    name = parts[0]
                    cmdline = parts[1] if len(parts) > 1 else ""
            except Exception:
                pass
        return name, cmdline

    def _is_cockpit_proc(name: str, cmdline: str) -> bool:
        combined = f"{name} {cmdline}".lower()
        cockpit_keywords = ["run_cockpit", "web_server:app", "agent-cockpit", "start_cockpit", "server.web_server"]
        return any(k in combined for k in cockpit_keywords)

    # Se não foi possível listar os PIDs (ex: lsof falhou por permissões),
    # mas o socket bind comprovou que a porta está ocupada:
    # NUNCA declarar como livre!
    if not listening_pids:
        if is_port_in_use(port=port, host=host):
            print("=" * 70)
            print(f"[!] AVISO DE CONFLITO: A porta {port} está ocupada no host {host}, mas não foi possível listar o PID.")
            print(f"[*] Pode ser necessário privilégio de root/administrador ou outro serviço do sistema.")
            print("=" * 70)
            return False
        return True

    # Inspeciona cada processo ouvindo na porta
    for pid in listening_pids:
        name, cmdline = _inspect_process(pid)
        is_ours = _is_cockpit_proc(name, cmdline)

        if is_ours or force:
            print(f"[*] Instância anterior do Agent Cockpit detectada (PID {pid}: {name}). Encerrando para reiniciar...")
            if sys.platform == "win32":
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(f"kill -9 {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)
        else:
            print("=" * 70)
            print(f"[!] AVISO DE SEGURANÇA: A porta {port} já está em uso por outro aplicativo!")
            print(f"[*] Processo detectado: {name} (PID: {pid})")
            if cmdline:
                print(f"[*] Linha de comando:   {cmdline}")
            print(f"[*] Por segurança, este processo NÃO pertence ao Cockpit e NÃO foi finalizado.")
            print("=" * 70)
            return False

    # Verificação final via socket bind antes de declarar a porta como livre
    return not is_port_in_use(port=port, host=host)


# =========================================================================
# CUSTOMIZATIONS & MCP / SKILLS MANAGER (ISSUE #16)
# =========================================================================

import shutil

try:
    import customizations_manager
    _CustomizationsManagerClass = getattr(customizations_manager, "CustomizationsManager", None)
except ImportError:
    try:
        from server import customizations_manager
        _CustomizationsManagerClass = getattr(customizations_manager, "CustomizationsManager", None)
    except ImportError:
        customizations_manager = None
        _CustomizationsManagerClass = None


class _FallbackCustomizationsManager:
    """Implementação resiliente de CustomizationsManager para gerenciamento em AppData."""

    def __init__(self, base_dir: Optional[str] = None):
        self._custom_base = base_dir
        self._lock = threading.Lock()

    @property
    def base_dir(self) -> str:
        if self._custom_base:
            return os.path.abspath(self._custom_base)
        if sys.platform == "win32":
            appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
            return os.path.join(appdata, "AgentCockpit", "customizations")
        config_dir = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        return os.path.join(config_dir, "agent-cockpit", "customizations")

    @property
    def mcp_dir(self) -> str:
        d = os.path.join(self.base_dir, "mcp")
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def skills_dir(self) -> str:
        d = os.path.join(self.base_dir, "skills")
        os.makedirs(d, exist_ok=True)
        return d

    def list_mcp_servers(self) -> List[Dict[str, Any]]:
        with self._lock:
            servers = []
            if not os.path.exists(self.mcp_dir):
                return servers
            for fname in sorted(os.listdir(self.mcp_dir)):
                if fname.endswith(".json"):
                    fpath = os.path.join(self.mcp_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                            if "id" not in cfg:
                                cfg["id"] = fname[:-5]
                            servers.append(cfg)
                    except Exception:
                        pass
            return servers

    def list_mcps(self) -> List[Dict[str, Any]]:
        return self.list_mcp_servers()

    def get_mcp_server(self, mcp_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            fpath = os.path.join(self.mcp_dir, f"{mcp_id}.json")
            if not os.path.exists(fpath):
                return None
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if "id" not in cfg:
                        cfg["id"] = mcp_id
                    return cfg
            except Exception:
                return None

    def get_mcp(self, mcp_id: str) -> Optional[Dict[str, Any]]:
        return self.get_mcp_server(mcp_id)

    def create_mcp_server(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            mcp_id = data.get("id") or data.get("name")
            data["id"] = mcp_id
            fpath = os.path.join(self.mcp_dir, f"{mcp_id}.json")
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return data

    def add_mcp_server(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.create_mcp_server(data)

    def create_mcp(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.create_mcp_server(data)

    def update_mcp_server(self, mcp_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            fpath = os.path.join(self.mcp_dir, f"{mcp_id}.json")
            if not os.path.exists(fpath):
                return None
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {"id": mcp_id}
            cfg.update({k: v for k, v in data.items() if v is not None})
            cfg["id"] = mcp_id
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            return cfg

    def update_mcp(self, mcp_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.update_mcp_server(mcp_id, data)

    def delete_mcp_server(self, mcp_id: str) -> bool:
        with self._lock:
            fpath = os.path.join(self.mcp_dir, f"{mcp_id}.json")
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                    return True
                except Exception:
                    return False
            return False

    def delete_mcp(self, mcp_id: str) -> bool:
        return self.delete_mcp_server(mcp_id)

    def toggle_mcp_server(self, mcp_id: str, enabled: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            fpath = os.path.join(self.mcp_dir, f"{mcp_id}.json")
            if not os.path.exists(fpath):
                return None
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                return None
            if enabled is None:
                cfg["enabled"] = not cfg.get("enabled", True)
            else:
                cfg["enabled"] = bool(enabled)
            cfg["id"] = mcp_id
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            return cfg

    def toggle_mcp(self, mcp_id: str, enabled: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        return self.toggle_mcp_server(mcp_id, enabled)

    def list_skills(self) -> List[Dict[str, Any]]:
        with self._lock:
            skills = []
            if not os.path.exists(self.skills_dir):
                return skills
            for entry in sorted(os.listdir(self.skills_dir)):
                entry_path = os.path.join(self.skills_dir, entry)
                if os.path.isdir(entry_path):
                    meta_path = os.path.join(entry_path, "metadata.json")
                    skill_md = os.path.join(entry_path, "SKILL.md")
                    meta = {"name": entry, "description": "", "enabled": True}
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path, "r", encoding="utf-8") as f:
                                meta.update(json.load(f))
                        except Exception:
                            pass
                    if os.path.exists(skill_md):
                        try:
                            with open(skill_md, "r", encoding="utf-8") as f:
                                meta["content"] = f.read()
                        except Exception:
                            meta["content"] = ""
                    meta["name"] = entry
                    skills.append(meta)
            return skills

    def get_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry_path = os.path.join(self.skills_dir, skill_name)
            if not os.path.isdir(entry_path):
                return None
            meta_path = os.path.join(entry_path, "metadata.json")
            skill_md = os.path.join(entry_path, "SKILL.md")
            meta = {"name": skill_name, "description": "", "enabled": True, "content": ""}
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta.update(json.load(f))
                except Exception:
                    pass
            if os.path.exists(skill_md):
                try:
                    with open(skill_md, "r", encoding="utf-8") as f:
                        meta["content"] = f.read()
                except Exception:
                    pass
            meta["name"] = skill_name
            return meta

    def create_skill(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            skill_name = (data.get("name") or "").strip()
            entry_path = os.path.join(self.skills_dir, skill_name)
            os.makedirs(entry_path, exist_ok=True)
            meta_path = os.path.join(entry_path, "metadata.json")
            skill_md = os.path.join(entry_path, "SKILL.md")

            content = data.get("content") or data.get("instructions") or ""
            with open(skill_md, "w", encoding="utf-8") as f:
                f.write(content)

            meta = {
                "name": skill_name,
                "description": data.get("description", ""),
                "enabled": data.get("enabled", True),
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

            meta["content"] = content
            return meta

    def add_skill(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.create_skill(data)

    def update_skill(self, skill_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry_path = os.path.join(self.skills_dir, skill_name)
            if not os.path.isdir(entry_path):
                return None
            meta_path = os.path.join(entry_path, "metadata.json")
            skill_md = os.path.join(entry_path, "SKILL.md")

            meta = {"name": skill_name, "description": "", "enabled": True}
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta.update(json.load(f))
                except Exception:
                    pass

            for k in ("description", "enabled"):
                if k in data and data[k] is not None:
                    meta[k] = data[k]

            meta["name"] = skill_name
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

            if "content" in data and data["content"] is not None:
                with open(skill_md, "w", encoding="utf-8") as f:
                    f.write(data["content"])
                meta["content"] = data["content"]
            elif os.path.exists(skill_md):
                with open(skill_md, "r", encoding="utf-8") as f:
                    meta["content"] = f.read()

            return meta

    def delete_skill(self, skill_name: str) -> bool:
        with self._lock:
            entry_path = os.path.join(self.skills_dir, skill_name)
            if os.path.isdir(entry_path):
                try:
                    shutil.rmtree(entry_path)
                    return True
                except Exception:
                    return False
            return False

    def toggle_skill(self, skill_name: str, enabled: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry_path = os.path.join(self.skills_dir, skill_name)
            if not os.path.isdir(entry_path):
                return None
            meta_path = os.path.join(entry_path, "metadata.json")
            meta = {"name": skill_name, "description": "", "enabled": True}
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta.update(json.load(f))
                except Exception:
                    pass
            if enabled is None:
                meta["enabled"] = not meta.get("enabled", True)
            else:
                meta["enabled"] = bool(enabled)
            meta["name"] = skill_name
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

            skill_md = os.path.join(entry_path, "SKILL.md")
            if os.path.exists(skill_md):
                try:
                    with open(skill_md, "r", encoding="utf-8") as f:
                        meta["content"] = f.read()
                except Exception:
                    pass
            return meta

    def sync(self) -> Dict[str, Any]:
        if opencode_manager and hasattr(opencode_manager, "sync_opencode_config"):
            try:
                return opencode_manager.sync_opencode_config()
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return {"status": "success", "mcp_synced": True, "skills_synced": True}

    def sync_all(self) -> Dict[str, Any]:
        return self.sync()


CustomizationsManager = _CustomizationsManagerClass or _FallbackCustomizationsManager
_customizations_mgr_instance = None


def get_customizations_mgr() -> Any:
    global _customizations_mgr_instance
    if _customizations_mgr_instance is None:
        _customizations_mgr_instance = CustomizationsManager()
    return _customizations_mgr_instance


def set_customizations_mgr(mgr: Any):
    global _customizations_mgr_instance
    _customizations_mgr_instance = mgr


class MCPServerPayload(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    type: str
    command: Optional[str] = None
    args: Optional[List[str]] = []
    env: Optional[Dict[str, str]] = {}
    url: Optional[str] = None
    enabled: Optional[bool] = True
    description: Optional[str] = ""


class MCPServerUpdatePayload(BaseModel):
    type: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None


class MCPTogglePayload(BaseModel):
    enabled: Optional[bool] = None


class SkillPayload(BaseModel):
    name: str
    description: Optional[str] = ""
    content: Optional[str] = ""
    instructions: Optional[str] = None
    enabled: Optional[bool] = True


class SkillUpdatePayload(BaseModel):
    description: Optional[str] = None
    content: Optional[str] = None
    instructions: Optional[str] = None
    enabled: Optional[bool] = None


class SkillTogglePayload(BaseModel):
    enabled: Optional[bool] = None


@app.get("/api/customizations/mcp")
def get_customizations_mcp():
    """Lista todos os servidores MCP configurados."""
    mgr = get_customizations_mgr()
    method = getattr(mgr, "list_mcp_servers", getattr(mgr, "list_mcps", None))
    servers = method() if callable(method) else []
    return {"status": "success", "mcp_servers": servers, "count": len(servers)}


@app.post("/api/customizations/mcp")
def post_customizations_mcp(payload: MCPServerPayload):
    """Cria um novo servidor MCP."""
    mcp_id = (payload.id or payload.name or "").strip()
    if not mcp_id:
        raise HTTPException(status_code=400, detail="ID ou nome do servidor MCP é obrigatório.")
    mcp_type = (payload.type or "").strip().lower()
    if mcp_type == "stdio" and not (payload.command and payload.command.strip()):
        raise HTTPException(status_code=400, detail="Comando é obrigatório para MCP do tipo stdio.")
    if mcp_type in ("sse", "http") and not (payload.url and payload.url.strip()):
        raise HTTPException(status_code=400, detail="URL é obrigatória para MCP do tipo sse/http.")

    mgr = get_customizations_mgr()
    data = payload.dict(exclude_unset=True)
    data["id"] = mcp_id
    method = getattr(mgr, "create_mcp_server", getattr(mgr, "add_mcp_server", getattr(mgr, "create_mcp", None)))
    if not callable(method):
        raise HTTPException(status_code=500, detail="Método de criação de MCP não disponível no manager.")
    try:
        res = method(data)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    manager.broadcast_sync("CUSTOMIZATIONS_MCP_UPDATED", {"action": "create", "mcp": res})
    return {"status": "success", "mcp_server": res, "message": f"Servidor MCP '{mcp_id}' criado com sucesso."}


@app.put("/api/customizations/mcp/{mcp_id}")
def put_customizations_mcp(mcp_id: str, payload: MCPServerUpdatePayload):
    """Atualiza configurações de um servidor MCP existente."""
    mgr = get_customizations_mgr()
    data = payload.dict(exclude_unset=True) if hasattr(payload, "dict") else payload.model_dump(exclude_unset=True)
    method = getattr(mgr, "update_mcp_server", getattr(mgr, "update_mcp", None))
    if not callable(method):
        raise HTTPException(status_code=500, detail="Método de atualização de MCP não disponível no manager.")
    try:
        res = method(mcp_id, data)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if res is None:
        raise HTTPException(status_code=404, detail=f"Servidor MCP '{mcp_id}' não encontrado.")
    manager.broadcast_sync("CUSTOMIZATIONS_MCP_UPDATED", {"action": "update", "mcp": res})
    return {"status": "success", "mcp_server": res, "message": f"Servidor MCP '{mcp_id}' atualizado com sucesso."}


@app.delete("/api/customizations/mcp/{mcp_id}")
def delete_customizations_mcp(mcp_id: str):
    """Exclui um servidor MCP configurado."""
    mgr = get_customizations_mgr()
    method = getattr(mgr, "delete_mcp_server", getattr(mgr, "delete_mcp", None))
    if not callable(method):
        raise HTTPException(status_code=500, detail="Método de exclusão de MCP não disponível no manager.")
    try:
        deleted = method(mcp_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Servidor MCP '{mcp_id}' não encontrado.")
    manager.broadcast_sync("CUSTOMIZATIONS_MCP_UPDATED", {"action": "delete", "mcp_id": mcp_id})
    return {"status": "success", "message": f"Servidor MCP '{mcp_id}' excluído com sucesso."}


@app.post("/api/customizations/mcp/{mcp_id}/toggle")
def toggle_customizations_mcp(mcp_id: str, payload: Optional[MCPTogglePayload] = None):
    """Ativa ou desativa um servidor MCP."""
    mgr = get_customizations_mgr()
    target_enabled = payload.enabled if payload else None
    method = getattr(mgr, "toggle_mcp_server", getattr(mgr, "toggle_mcp", None))
    if not callable(method):
        raise HTTPException(status_code=500, detail="Método toggle de MCP não disponível no manager.")
    try:
        res = method(mcp_id, enabled=target_enabled)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if res is None:
        raise HTTPException(status_code=404, detail=f"Servidor MCP '{mcp_id}' não encontrado.")
    manager.broadcast_sync("CUSTOMIZATIONS_MCP_UPDATED", {"action": "toggle", "mcp": res})
    return {
        "status": "success",
        "mcp_id": mcp_id,
        "enabled": res.get("enabled", False),
        "mcp_server": res,
        "message": f"Servidor MCP '{mcp_id}' {'ativado' if res.get('enabled') else 'desativado'} com sucesso."
    }


@app.get("/api/customizations/skills")
def get_customizations_skills():
    """Lista todas as skills configuradas."""
    mgr = get_customizations_mgr()
    method = getattr(mgr, "list_skills", None)
    skills = method() if callable(method) else []
    return {"status": "success", "skills": skills, "count": len(skills)}


@app.post("/api/customizations/skills")
def post_customizations_skills(payload: SkillPayload):
    """Cria uma nova Skill com instruções SKILL.md."""
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome da skill é obrigatório.")
    mgr = get_customizations_mgr()
    data = payload.dict(exclude_unset=True) if hasattr(payload, "dict") else payload.model_dump(exclude_unset=True)
    data["name"] = name
    method = getattr(mgr, "create_skill", getattr(mgr, "add_skill", None))
    if not callable(method):
        raise HTTPException(status_code=500, detail="Método de criação de skill não disponível no manager.")
    try:
        res = method(data)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    manager.broadcast_sync("CUSTOMIZATIONS_SKILLS_UPDATED", {"action": "create", "skill": res})
    return {"status": "success", "skill": res, "message": f"Skill '{name}' criada com sucesso."}


@app.put("/api/customizations/skills/{skill_name}")
def put_customizations_skills(skill_name: str, payload: SkillUpdatePayload):
    """Atualiza metadados e conteúdo de uma Skill existente."""
    mgr = get_customizations_mgr()
    data = payload.dict(exclude_unset=True) if hasattr(payload, "dict") else payload.model_dump(exclude_unset=True)
    method = getattr(mgr, "update_skill", None)
    if not callable(method):
        raise HTTPException(status_code=500, detail="Método de atualização de skill não disponível no manager.")
    try:
        res = method(skill_name, data)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if res is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' não encontrada.")
    manager.broadcast_sync("CUSTOMIZATIONS_SKILLS_UPDATED", {"action": "update", "skill": res})
    return {"status": "success", "skill": res, "message": f"Skill '{skill_name}' atualizada com sucesso."}


@app.delete("/api/customizations/skills/{skill_name}")
def delete_customizations_skills(skill_name: str):
    """Exclui uma Skill existente."""
    mgr = get_customizations_mgr()
    method = getattr(mgr, "delete_skill", None)
    if not callable(method):
        raise HTTPException(status_code=500, detail="Método de exclusão de skill não disponível no manager.")
    try:
        deleted = method(skill_name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' não encontrada.")
    manager.broadcast_sync("CUSTOMIZATIONS_SKILLS_UPDATED", {"action": "delete", "skill_name": skill_name})
    return {"status": "success", "message": f"Skill '{skill_name}' excluída com sucesso."}


@app.post("/api/customizations/skills/{skill_name}/toggle")
def toggle_customizations_skills(skill_name: str, payload: Optional[SkillTogglePayload] = None):
    """Ativa ou desativa uma Skill."""
    mgr = get_customizations_mgr()
    target_enabled = payload.enabled if payload else None
    method = getattr(mgr, "toggle_skill", None)
    if not callable(method):
        raise HTTPException(status_code=500, detail="Método toggle de skill não disponível no manager.")
    try:
        res = method(skill_name, enabled=target_enabled)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if res is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' não encontrada.")
    manager.broadcast_sync("CUSTOMIZATIONS_SKILLS_UPDATED", {"action": "toggle", "skill": res})
    return {
        "status": "success",
        "name": skill_name,
        "enabled": res.get("enabled", False),
        "skill": res,
        "message": f"Skill '{skill_name}' {'ativada' if res.get('enabled') else 'desativada'} com sucesso."
    }


@app.post("/api/customizations/sync")
def post_customizations_sync():
    """Executa sincronização imediata de MCPs e Skills com o OpenCode."""
    mgr = get_customizations_mgr()
    sync_result = {}
    if hasattr(mgr, "sync_all"):
        sync_result = mgr.sync_all()
    elif hasattr(mgr, "sync"):
        sync_result = mgr.sync()
    elif hasattr(mgr, "sync_opencode"):
        sync_result = mgr.sync_opencode()
    else:
        sync_result = {"mcp_synced": True, "skills_synced": True}
    manager.broadcast_sync("CUSTOMIZATIONS_SYNCED", sync_result)
    return {"status": "success", "synced": True, "result": sync_result, "message": "Customizações sincronizadas com sucesso."}


# --- MÉTODOS DE SUPORTE NO STATESTORE (Issue #17 Fatia 2) ---
from state_store import StateStore

if not hasattr(StateStore, "get_general_defaults"):
    def _store_get_general_defaults(self) -> Dict[str, Any]:
        with self.lock:
            gov = self.get_governance_settings("default")
            st = self.get_settings("default")
            return {
                "autostart_slices": gov.get("autostart_slices", False),
                "security_preset": gov.get("security_preset", "standard"),
                "human_gate_policy": gov.get("human_gate_policy", "manual"),
                "artifact_review_policy": gov.get("artifact_review_policy", "strict"),
                "enable_local_ai": st.get("enable_local_ai", False),
                "delegate_styles_to_cloud": st.get("delegate_styles_to_cloud", True),
                "model": st.get("model", "deepseek-coder-v2:16b-q3_k_m"),
                "endpoint": st.get("endpoint", "http://127.0.0.1:11434"),
                "auto_start_ollama": st.get("auto_start_ollama", False),
                "circuit_breaker_threshold": st.get("circuit_breaker_threshold", 2),
                "project_root": st.get("project_root")
            }
    StateStore.get_general_defaults = _store_get_general_defaults

if not hasattr(StateStore, "get_project_settings"):
    def _store_get_project_settings(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            overrides = dict(state.get("project_settings_overrides", {}))
            general_defaults = self.get_general_defaults()
            effective = dict(general_defaults)
            for k, v in overrides.items():
                if v is not None:
                    effective[k] = v
            return {
                "project_id": target_pid,
                "overrides": overrides,
                "general_defaults": general_defaults,
                "effective_settings": effective
            }
    StateStore.get_project_settings = _store_get_project_settings

if not hasattr(StateStore, "set_project_settings"):
    def _store_set_project_settings(self, project_id: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            current_overrides = state.setdefault("project_settings_overrides", {})
            if overrides:
                for k, v in overrides.items():
                    if v is None:
                        current_overrides.pop(k, None)
                    else:
                        current_overrides[k] = v
            self._save_state(state, target_pid)
            res = self.get_project_settings(target_pid)
        self._notify("PROJECT_SETTINGS_UPDATED", res, target_pid)
        return res
    StateStore.set_project_settings = _store_set_project_settings

if not hasattr(StateStore, "clear_project_settings_overrides"):
    def _store_clear_project_settings_overrides(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            state["project_settings_overrides"] = {}
            self._save_state(state, target_pid)
            res = self.get_project_settings(target_pid)
        self._notify("PROJECT_SETTINGS_UPDATED", res, target_pid)
        return res
    StateStore.clear_project_settings_overrides = _store_clear_project_settings_overrides


# --- ROTAS REST PARA CONFIGURAÇÕES DE PROJETO (Issue #17 Fatia 2) ---

@app.get("/api/projects/{project_id}/settings")
def get_project_settings_endpoint(project_id: str):
    """Retorna status 200 com project_id, effective_settings, overrides e general_defaults."""
    try:
        return db.get_project_settings(project_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/projects/{project_id}/settings")
@app.post("/api/projects/{project_id}/settings")
def update_project_settings_endpoint(project_id: str, payload: Dict[str, Any]):
    """Salva overrides de configurações para o projeto especificado e retorna os valores efetivos."""
    try:
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Payload inválido: deve ser um objeto JSON.")
        overrides = payload.get("overrides") if isinstance(payload.get("overrides"), dict) else payload
        clean_overrides = {k: v for k, v in overrides.items() if k != "project_id"}
        res = db.set_project_settings(project_id, clean_overrides)
        manager.broadcast_sync("PROJECT_SETTINGS_UPDATED", res, project_id)
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/projects/{project_id}/settings/overrides")
def clear_project_settings_overrides_endpoint(project_id: str):
    """Limpa todos os overrides de um projeto restaurando herança total de General."""
    try:
        res = db.clear_project_settings_overrides(project_id)
        manager.broadcast_sync("PROJECT_SETTINGS_UPDATED", res, project_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# Issue #24 (Fatia 1): Zeus Chat Engine, Multimodal & Ultra-lightweight STT
# =====================================================================

@app.post("/api/zeus-chat/message")
async def post_zeus_chat_message_endpoint(req: Dict[str, Any] = Body(...)):
    """Executa prompt com streaming Server-Sent Events (SSE) e eventos estruturados."""
    if not zeus_chat_engine:
        raise HTTPException(status_code=500, detail="Módulo zeus_chat_engine não disponível.")

    session_id = req.get("session_id") or str(uuid.uuid4())
    message = req.get("message", "")
    model_id = req.get("model_id", "auto")
    backend = req.get("backend", "auto")
    images = req.get("images", [])
    system_prompt = req.get("system_prompt")

    if images and model_id != "auto":
        if not zeus_chat_engine.is_vision_model(model_id):
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": f"O modelo '{model_id}' não suporta visão multimodal."}
            )

    event_generator = zeus_chat_engine.zeus_engine.stream_chat_sse(
        session_id=session_id,
        message=message,
        model_id=model_id,
        backend=backend,
        images=images,
        system_prompt=system_prompt,
        broadcast_callback=manager.broadcast_sync
    )

    return StreamingResponse(
        event_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/audio/transcribe-and-optimize")
async def post_audio_transcribe_and_optimize_endpoint(request: Request):
    """
    STT ultraleve em RAM (CPU-only, não consome GPU VRAM) + Otimizador de Prompts.
    Suporta payload em JSON (base64) ou multipart/form-data.
    """
    if not zeus_chat_engine:
        raise HTTPException(status_code=500, detail="Módulo zeus_chat_engine não disponível.")

    content_type = request.headers.get("content-type", "")
    audio_bytes = b""
    hint = None

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="JSON inválido.")
        b64_str = body.get("audio_base64") or body.get("audio") or body.get("audio_data") or ""
        hint = body.get("hint") or body.get("text_hint") or body.get("prompt_hint")
        if b64_str:
            if "," in b64_str:
                b64_str = b64_str.split(",", 1)[1]
            try:
                audio_bytes = base64.b64decode(b64_str)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Erro ao decodificar áudio em base64: {str(e)}")
    elif "multipart/form-data" in content_type:
        raw_body = await request.body()
        audio_bytes, hint = zeus_chat_engine.zeus_engine.extract_audio_from_multipart(raw_body, content_type)
    else:
        # Fallback para raw audio stream direto
        audio_bytes = await request.body()
        hint = request.headers.get("x-audio-hint")

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Nenhum dado de áudio fornecido.")

    res = zeus_chat_engine.zeus_engine.transcribe_and_optimize(audio_bytes=audio_bytes, hint=hint)
    return res


@app.post("/api/chat/validate-multimodal")
def post_chat_validate_multimodal_endpoint(payload: Dict[str, Any] = Body(...)):
    """Valida se o modelo suporta visão multimodal e checa integridade de imagem se fornecida."""
    if not zeus_chat_engine:
        raise HTTPException(status_code=500, detail="Módulo zeus_chat_engine não disponível.")

    model_id = payload.get("model_id", "")
    image = payload.get("image") or payload.get("image_url") or payload.get("image_data")

    supported = zeus_chat_engine.is_vision_model(model_id)
    if not supported:
        return {
            "status": "ok",
            "supported": False,
            "message": "O modelo selecionado não suporta visão multimodal.",
            "model_id": model_id
        }

    image_info = None
    if image:
        val = zeus_chat_engine.validate_image_payload(image)
        if not val.get("valid"):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "supported": True,
                    "message": f"Payload de imagem inválido: {val.get('error')}",
                    "model_id": model_id
                }
            )
        image_info = val

    return {
        "status": "ok",
        "supported": True,
        "message": "Modelo compatível com visão multimodal.",
        "model_id": model_id,
        "image_info": image_info
    }


@app.get("/api/zeus-chat/session/{session_id}/history")
def get_zeus_chat_history_endpoint(session_id: str):
    """Retorna o histórico estruturado de conversas da sessão."""
    if not zeus_chat_engine:
        raise HTTPException(status_code=500, detail="Módulo zeus_chat_engine não disponível.")

    history = zeus_chat_engine.zeus_engine.get_history(session_id)
    return {
        "status": "ok",
        "session_id": session_id,
        "history": history,
        "count": len(history)
    }


@app.delete("/api/zeus-chat/session/{session_id}")
def delete_zeus_chat_session_endpoint(session_id: str):
    """Limpa ou remove uma sessão do Zeus Chat."""
    if not zeus_chat_engine:
        raise HTTPException(status_code=500, detail="Módulo zeus_chat_engine não disponível.")

    success = zeus_chat_engine.zeus_engine.session_manager.delete_session(session_id)
    return {"status": "ok", "deleted": success, "session_id": session_id}


# Garante que o mount de arquivos estáticos permaneça no final da lista de rotas
for _r in list(app.router.routes):
    if getattr(_r, "name", None) == "web":
        app.router.routes.remove(_r)
        app.router.routes.append(_r)
        break



