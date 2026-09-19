"""
models.py: Endpoints para modelos locais, ciclo de vida do servidor Ollama e Hugging Face Hub.
"""

import os
import sys
import json
import asyncio
import threading
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from state_store import db
from connection_manager import manager

# WORKER QUEUE
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

# OLLAMA PROCESS MANAGER
try:
    from workers.ollama_process_manager import OllamaProcessManager
except ImportError:
    try:
        from server.workers.ollama_process_manager import OllamaProcessManager
    except ImportError:
        OllamaProcessManager = None


def _on_ollama_log(line: str):
    _resolve_broadcast()("ollama_log", {"line": line})


if OllamaProcessManager:
    try:
        ollama_process_manager = OllamaProcessManager(log_callback=_on_ollama_log)
    except TypeError:
        ollama_process_manager = OllamaProcessManager()
        if hasattr(ollama_process_manager, "set_log_callback"):
            ollama_process_manager.set_log_callback(_on_ollama_log)
        else:
            ollama_process_manager.log_callback = _on_ollama_log
else:
    ollama_process_manager = None


def _get_ollama_mgr():
    ws = sys.modules.get("web_server")
    return getattr(ws, "ollama_process_manager", ollama_process_manager) if ws else ollama_process_manager


def _resolve_broadcast():
    ws = sys.modules.get("web_server")
    return getattr(getattr(ws, "manager", None), "broadcast_sync", manager.broadcast_sync) if ws else manager.broadcast_sync


async def auto_start_ollama_task():
    try:
        cfg = db.get_local_worker_config() if hasattr(db, "get_local_worker_config") else {}
        settings = db.get_settings() if hasattr(db, "get_settings") else {}
        is_local_ai = bool(cfg.get("enabled", False) or settings.get("enable_local_ai", False))
        auto_start = cfg.get("auto_start_ollama", False) if is_local_ai else False
        if os.getenv("COCKPIT_NO_OLLAMA") == "1":
            auto_start = False

        mgr = _get_ollama_mgr()
        if auto_start and mgr and mgr.is_installed():
            if not mgr.is_port_open():
                print("[Ollama] Detectado binário instalado e porta 11434 fechada. Iniciando em background...")
                loop = asyncio.get_running_loop()
                res = await loop.run_in_executor(None, mgr.start)
                print(f"[Ollama] Inicialização em background concluída: {res.get('status') if isinstance(res, dict) else res}")
                status = mgr.get_status() if hasattr(mgr, "get_status") else {}
                _resolve_broadcast()("ollama_status", status)
    except Exception as e:
        print(f"[Ollama] Erro durante inicialização em background: {e}")


# LOCAL LLM CLIENT
try:
    from workers.local_llm_client import LocalLLMClient
except ImportError:
    try:
        from server.workers.local_llm_client import LocalLLMClient
    except ImportError:
        LocalLLMClient = None


def _get_local_worker_client(project_id: Optional[str] = None):
    cfg = db.get_local_worker_config(project_id) if hasattr(db, "get_local_worker_config") else db.get_state(project_id).get("local_worker", {
        "provider": "ollama", "endpoint": "http://127.0.0.1:11434",
        "model": "qwen2.5-coder:7b-instruct-q4_k_m", "circuit_breaker_threshold": 2, "consecutive_failures": {}
    })
    endpoint = cfg.get("endpoint", "http://127.0.0.1:11434")
    if LocalLLMClient:
        return LocalLLMClient(base_url=endpoint), cfg

    class _FallbackLocalLLMClient:
        def __init__(self, base_url="http://127.0.0.1:11434", timeout=5.0):
            self.base_url = base_url.rstrip("/")
            self.timeout = timeout
        def healthcheck(self) -> bool:
            import urllib.request
            try:
                with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=self.timeout) as resp:
                    return resp.getcode() == 200
            except Exception:
                return False
        def list_models(self) -> Dict[str, Any]:
            import urllib.request
            try:
                with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    installed = [m.get("name", "") for m in data.get("models", []) if "name" in m]
                    return {"online": True, "installed": installed, "recommended": []}
            except Exception:
                return {"online": False, "installed": [], "recommended": []}
        def pull_model(self, model_name: str, stream: bool = False, progress_callback=None) -> Dict[str, Any]:
            return {"status": "ok"}

    return _FallbackLocalLLMClient(base_url=endpoint), cfg


def _resolve_get_client():
    ws = sys.modules.get("web_server")
    return getattr(ws, "_get_local_worker_client", _get_local_worker_client) if ws else _get_local_worker_client


# HF HUB CLIENT
try:
    from workers.hf_hub_client import HFHubClient
except ImportError:
    try:
        from server.workers.hf_hub_client import HFHubClient
    except ImportError:
        HFHubClient = None

router = APIRouter(tags=["models"])


class LocalWorkerSelectPayload(BaseModel):
    model: str
    project_id: Optional[str] = None


class LocalWorkerPullPayload(BaseModel):
    model: str
    project_id: Optional[str] = None


@router.get("/api/local-worker/queue")
def get_local_worker_queue(slice_id: Optional[str] = None, ticket_id: Optional[str] = None):
    if local_worker_queue:
        return local_worker_queue.get_queue_status(slice_id=slice_id, ticket_id=ticket_id)
    try:
        from workers.worker_queue import DEFAULT_SNAPSHOT_PATH
        if os.path.exists(DEFAULT_SNAPSHOT_PATH):
            with open(DEFAULT_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"is_busy": False, "active_task": None, "queue_length": 0, "queued_tasks": [], "your_position": None, "message": "Fila do Local Worker não inicializada."}


@router.get("/api/local-worker/status")
def get_local_worker_status(project_id: Optional[str] = None):
    client, cfg = _resolve_get_client()(project_id)
    res = {
        "status": "ok", "online": client.healthcheck(), "provider": cfg.get("provider", "ollama"),
        "endpoint": cfg.get("endpoint", "http://127.0.0.1:11434"), "model": cfg.get("model", "qwen2.5-coder:7b-instruct-q4_k_m"),
        "circuit_breaker_threshold": cfg.get("circuit_breaker_threshold", 2), "consecutive_failures": cfg.get("consecutive_failures", {}),
        "auto_start_ollama": cfg.get("auto_start_ollama", True), "delegate_styles_to_cloud": cfg.get("delegate_styles_to_cloud", False)
    }
    mgr = _get_ollama_mgr()
    if mgr and hasattr(mgr, "get_status"):
        res["server_status"] = mgr.get_status()
    return res


@router.post("/api/local-worker/start-server")
def post_local_worker_start_server():
    mgr = _get_ollama_mgr()
    if not mgr:
        return {"status": "ERROR", "error": "OllamaProcessManager não está disponível.", "installed": False}
    try:
        res = mgr.start()
        status = mgr.get_status() if hasattr(mgr, "get_status") else {}
        _resolve_broadcast()("ollama_status", status)
        return res
    except (RuntimeError, Exception) as e:
        status = mgr.get_status() if (mgr and hasattr(mgr, "get_status")) else {"installed": False, "running": False}
        _resolve_broadcast()("ollama_status", status)
        return {"status": "ERROR", "error": str(e), "installed": False}


@router.post("/api/local-worker/stop-server")
def post_local_worker_stop_server():
    mgr = _get_ollama_mgr()
    if not mgr:
        return {"status": "ERROR", "error": "OllamaProcessManager não está disponível.", "installed": False}
    try:
        res = mgr.stop()
        status = mgr.get_status() if hasattr(mgr, "get_status") else {}
        _resolve_broadcast()("ollama_status", status)
        return res
    except (RuntimeError, Exception) as e:
        status = mgr.get_status() if (mgr and hasattr(mgr, "get_status")) else {"installed": False, "running": False}
        _resolve_broadcast()("ollama_status", status)
        return {"status": "ERROR", "error": str(e), "installed": status.get("installed", False)}


@router.get("/api/local-worker/server-logs")
def get_local_worker_server_logs(limit: int = 100):
    mgr = _get_ollama_mgr()
    if not mgr or not hasattr(mgr, "get_logs"):
        return {"status": "unavailable", "logs": [], "count": 0}
    logs = mgr.get_logs(limit=limit)
    status = mgr.get_status() if hasattr(mgr, "get_status") else {}
    return {"status": "ok", "logs": logs, "count": len(logs), "running": status.get("running", False),
            "managed_by_cockpit": status.get("managed_by_cockpit", False), "installed": status.get("installed", False)}


@router.get("/api/local-worker/models")
def get_local_worker_models(project_id: Optional[str] = None):
    client, cfg = _resolve_get_client()(project_id)
    models_info = client.list_models()
    return {"status": "ok", "online": models_info.get("online", False), "installed": models_info.get("installed", []),
            "recommended": models_info.get("recommended", []), "current_model": cfg.get("model", "qwen2.5-coder:7b-instruct-q4_k_m")}


@router.post("/api/local-worker/select")
def post_local_worker_select(payload: LocalWorkerSelectPayload):
    model_name = payload.model.strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="Nome do modelo não pode ser vazio.")
    if hasattr(db, "set_local_worker_config"):
        cfg = db.set_local_worker_config({"model": model_name}, project_id=payload.project_id)
    else:
        target_pid = db.resolve_project_id(payload.project_id)
        with db.lock:
            state = db.get_state(target_pid)
            cfg = state.setdefault("local_worker", {
                "provider": "ollama", "endpoint": "http://127.0.0.1:11434",
                "model": "qwen2.5-coder:7b-instruct-q4_k_m", "circuit_breaker_threshold": 2, "consecutive_failures": {}
            })
            cfg["model"] = model_name
            db._save_state(state, target_pid)
        db._notify("LOCAL_WORKER_CONFIG_UPDATED", cfg, target_pid)
        db._notify("STATE_FULL", state, target_pid)
    return {"status": "ok", "model": model_name, "config": cfg}


@router.post("/api/local-worker/pull")
def post_local_worker_pull(payload: LocalWorkerPullPayload):
    model_name = payload.model.strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="Nome do modelo não pode ser vazio.")
    client, _ = _resolve_get_client()(payload.project_id)
    bcast = _resolve_broadcast()

    def _bg_pull():
        def on_progress(chunk: dict):
            bcast("model_pull_progress", {"model": model_name, "progress": chunk})
        try:
            res = client.pull_model(model_name, stream=True, progress_callback=on_progress)
            if isinstance(res, dict) and (res.get("status") == "error" or "error" in res):
                err_msg = res.get("message") or res.get("error") or "Falha ao baixar modelo"
                bcast("model_pull_complete", {"model": model_name, "status": "error", "message": err_msg})
            else:
                bcast("model_pull_complete", {"model": model_name, "status": "success"})
        except Exception as e:
            bcast("model_pull_complete", {"model": model_name, "status": "error", "message": str(e)})

    threading.Thread(target=_bg_pull, daemon=True).start()
    return {"status": "pulling", "model": model_name, "message": f"Download de '{model_name}' iniciado em segundo plano no Ollama. Acompanhe o progresso no Console de Logs."}


@router.get("/api/local-worker/hf-search")
@router.get("/api/models/hf")
@router.get("/api/huggingface/models")
def get_local_worker_hf_search(query: str = "", limit: int = 20):
    results = HFHubClient().search_models(query=query, limit=limit) if HFHubClient else []
    return {"query": query, "count": len(results), "models": results}
