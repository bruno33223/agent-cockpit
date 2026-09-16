import os
import sys
import json
import time
import socket
import asyncio
import threading
import mimetypes
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
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
    asyncio.create_task(auto_start_ollama_task())

@app.on_event("shutdown")
async def shutdown_event():
    """Ao encerrar o Cockpit, finaliza o processo do Ollama se foi iniciado pelo Cockpit."""
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
    """Retorna o status atual da fila de tarefas da GPU do Local Worker."""
    if local_worker_queue:
        return local_worker_queue.get_queue_status(slice_id=slice_id, ticket_id=ticket_id)
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
    await websocket.accept()
    
    if not pty_session_manager:
        await websocket.send_text("\r\n[Erro: Suporte PTY indisponível nesta plataforma]\r\n")
        await websocket.close()
        return

    target_pid = project_id or db.get_current_project_id()
    # Determina diretório de trabalho do projeto ativo se não fornecido
    if not cwd:
        root_path, _, _ = _resolve_project_fs_root(target_pid)
        target_slice = slice_id or task_id
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

    if not cwd:
        root_path, _, _ = _resolve_project_fs_root(project_id)
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
