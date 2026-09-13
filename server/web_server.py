import os
import sys
import json
import time
import socket
import asyncio
import threading
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

# Monta arquivos estáticos do dashboard visual
WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))
if os.path.exists(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
