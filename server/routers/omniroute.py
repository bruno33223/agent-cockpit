"""
omniroute.py: Endpoints de integração com OmniRoute proxy, OpenCode CLI e sessões headless.
"""

import sys
from typing import Optional, Dict, Any
from fastapi import APIRouter, Body
from pydantic import BaseModel

from state_store import db
from connection_manager import manager

try:
    import opencode_manager
except ImportError:
    try:
        from server import opencode_manager
    except ImportError:
        opencode_manager = None


def _get_opencode_mgr():
    ws = sys.modules.get("web_server")
    if ws and hasattr(ws, "opencode_manager"):
        return ws.opencode_manager
    return opencode_manager


router = APIRouter(tags=["omniroute"])


class OmniRouteConfigPayload(BaseModel):
    omniroute_url: Optional[str] = "http://localhost:20128/v1"
    api_key: Optional[str] = "omniroute-local"
    model: Optional[str] = "auto"
    enabled: Optional[bool] = True


class OmniRouteAccountPayload(BaseModel):
    provider: str
    name: Optional[str] = None
    api_key: Optional[str] = None
    default_model: Optional[str] = None
    provider_specific_data: Optional[Dict[str, Any]] = None


class OmniRouteOAuthStartPayload(BaseModel):
    provider: str
    base_url: Optional[str] = None


class OmniRouteOAuthFinishPayload(BaseModel):
    provider: str
    code: str
    code_verifier: Optional[str] = None
    redirect_uri: Optional[str] = None
    state: Optional[str] = None
    base_url: Optional[str] = None


class OmniRouteOAuthImportPayload(BaseModel):
    provider: Optional[str] = "cursor"
    base_url: Optional[str] = None


@router.get("/api/omniroute/oauth/providers")
def get_omniroute_oauth_providers():
    mgr = _get_opencode_mgr()
    if mgr and hasattr(mgr, "list_omniroute_oauth_providers"):
        return {"providers": mgr.list_omniroute_oauth_providers()}
    return {"providers": []}


@router.post("/api/omniroute/oauth/start")
def post_omniroute_oauth_start(payload: OmniRouteOAuthStartPayload):
    mgr = _get_opencode_mgr()
    if mgr and hasattr(mgr, "start_omniroute_oauth"):
        return mgr.start_omniroute_oauth(payload.provider, payload.base_url)
    return {"status": "error", "message": "Módulo indisponível"}


@router.post("/api/omniroute/oauth/finish")
def post_omniroute_oauth_finish(payload: OmniRouteOAuthFinishPayload):
    mgr = _get_opencode_mgr()
    if mgr and hasattr(mgr, "finish_omniroute_oauth"):
        data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
        return mgr.finish_omniroute_oauth(data, payload.base_url)
    return {"status": "error", "message": "Módulo indisponível"}


@router.post("/api/omniroute/oauth/import-local")
def post_omniroute_oauth_import_local(payload: OmniRouteOAuthImportPayload):
    mgr = _get_opencode_mgr()
    if mgr and hasattr(mgr, "import_omniroute_local_credentials"):
        return mgr.import_omniroute_local_credentials(payload.provider or "cursor", payload.base_url)
    return {"status": "error", "message": "Módulo indisponível"}


@router.get("/api/omniroute/daemon/status")
def get_omniroute_daemon_status():
    mgr = _get_opencode_mgr()
    if mgr and hasattr(mgr, "get_omniroute_daemon_status"):
        return mgr.get_omniroute_daemon_status()
    return {"installed": False, "running": False, "url": "http://localhost:20128", "message": "Módulo indisponível"}


@router.post("/api/omniroute/daemon/start")
def post_omniroute_daemon_start():
    mgr = _get_opencode_mgr()
    if mgr and hasattr(mgr, "start_omniroute_daemon"):
        return mgr.start_omniroute_daemon()
    return {"status": "error", "message": "Módulo indisponível"}


@router.get("/api/omniroute/accounts")
def get_omniroute_accounts(base_url: Optional[str] = None):
    mgr = _get_opencode_mgr()
    if mgr and hasattr(mgr, "list_omniroute_accounts"):
        accounts = mgr.list_omniroute_accounts(base_url)
        return {"accounts": accounts, "count": len(accounts)}
    return {"accounts": [], "count": 0}


@router.post("/api/omniroute/accounts")
def post_omniroute_account(payload: OmniRouteAccountPayload, base_url: Optional[str] = None):
    mgr = _get_opencode_mgr()
    if mgr and hasattr(mgr, "add_omniroute_account"):
        data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
        return mgr.add_omniroute_account(data, base_url)
    return {"status": "error", "message": "Módulo indisponível"}


@router.delete("/api/omniroute/accounts/{account_id}")
def delete_omniroute_account(account_id: str, base_url: Optional[str] = None):
    mgr = _get_opencode_mgr()
    if mgr and hasattr(mgr, "delete_omniroute_account"):
        return mgr.delete_omniroute_account(account_id, base_url)
    return {"status": "error", "message": "Módulo indisponível"}


@router.post("/api/omniroute/accounts/{account_id}/test")
def test_omniroute_account(account_id: str, base_url: Optional[str] = None):
    mgr = _get_opencode_mgr()
    if mgr and hasattr(mgr, "test_omniroute_account"):
        return mgr.test_omniroute_account(account_id, base_url)
    return {"valid": False, "status": "error", "message": "Módulo indisponível"}


@router.get("/api/omniroute/models")
def get_omniroute_models(base_url: Optional[str] = None):
    mgr = _get_opencode_mgr()
    if mgr and hasattr(mgr, "list_omniroute_live_models"):
        return mgr.list_omniroute_live_models(base_url)
    return {"status": "error", "models": [], "connectors": [], "active_model": "auto"}


@router.get("/api/omniroute/status")
def get_omniroute_status(base_url: Optional[str] = None):
    mgr = _get_opencode_mgr()
    if mgr:
        return mgr.check_omniroute_health(base_url)
    return {"online": False, "models": [], "message": "Módulo opencode_manager não disponível"}


@router.get("/api/omniroute/config")
def get_omniroute_config():
    mgr = _get_opencode_mgr()
    if mgr:
        return mgr.load_config()
    return {"omniroute_url": "http://localhost:20128/v1", "api_key": "omniroute-local", "model": "auto"}


@router.post("/api/omniroute/config")
def post_omniroute_config(payload: OmniRouteConfigPayload):
    mgr = _get_opencode_mgr()
    if mgr:
        data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
        res = mgr.save_config(data)
        manager.broadcast_sync("OMNIROUTE_CONFIG_UPDATED", res)
        return {"status": "success", "config": res}
    return {"status": "error", "message": "Módulo opencode_manager não disponível"}


@router.get("/api/opencode/binaries")
def get_opencode_binaries():
    mgr = _get_opencode_mgr()
    if mgr:
        return mgr.detect_binaries()
    return {"opencode": {"installed": False}, "omniroute": {"installed": False}}


@router.get("/api/opencode/models")
def get_opencode_models():
    mgr = _get_opencode_mgr()
    if mgr and hasattr(mgr, "list_opencode_models"):
        return mgr.list_opencode_models()
    return {"status": "error", "models": [], "count": 0, "message": "Módulo opencode_manager não disponível"}


@router.post("/api/opencode/sync-config")
def post_opencode_sync():
    mgr = _get_opencode_mgr()
    if mgr:
        return mgr.sync_opencode_config()
    return {"status": "error", "message": "Módulo opencode_manager não disponível"}


@router.get("/api/omniroute/connectors")
def get_omniroute_connectors(base_url: Optional[str] = None):
    mgr = _get_opencode_mgr()
    if mgr:
        connectors = mgr.detect_omniroute_connectors(base_url)
        return {"online": bool(connectors), "connectors": connectors, "count": len(connectors)}
    return {"online": False, "connectors": [], "count": 0, "message": "Módulo opencode_manager não disponível"}


@router.get("/api/opencode/credentials")
def get_opencode_credentials():
    mgr = _get_opencode_mgr()
    if mgr:
        return mgr.detect_opencode_credentials()
    return {"omniroute_url": None, "api_key": None, "model": None, "sources": []}


@router.get("/api/opencode/detect")
def get_opencode_detect():
    creds = get_opencode_credentials()
    return {"status": "ok", "credentials": creds}


@router.post("/api/opencode/headless/start")
def post_opencode_headless_start(req: Optional[Dict[str, Any]] = Body(default={})):
    req_data = req or {}
    mgr = _get_opencode_mgr()
    if mgr:
        res = mgr.start_headless_session(
            session_id=req_data.get("session_id"), prompt=req_data.get("prompt"), cwd=req_data.get("cwd"),
            model=req_data.get("model"), project_id=req_data.get("project_id") or db.get_current_project_id(),
            broadcast_callback=manager.broadcast_sync
        )
        return {"status": "ok", "session_id": res.get("session_id"), "running": res.get("running", True), "data": res}
    return {"status": "error", "message": "Módulo opencode_manager não disponível"}


@router.post("/api/opencode/headless/message")
def post_opencode_headless_message(req: Dict[str, Any] = Body(...)):
    session_id = req.get("session_id")
    if not session_id:
        return {"status": "error", "message": "session_id é obrigatório"}
    mgr = _get_opencode_mgr()
    if mgr:
        res = mgr.send_headless_message(session_id=session_id, message=req.get("message", ""), broadcast_callback=manager.broadcast_sync)
        return {"status": "ok", "session_id": session_id, "message": req.get("message", ""), "data": res}
    return {"status": "error", "message": "Módulo opencode_manager não disponível"}


@router.get("/api/opencode/headless/subagents")
def get_opencode_headless_subagents(session_id: Optional[str] = None):
    mgr = _get_opencode_mgr()
    if mgr:
        subagents = mgr.list_subagents(parent_session_id=session_id)
        return {"status": "ok", "subagents": subagents, "count": len(subagents)}
    return {"status": "error", "subagents": [], "count": 0, "message": "Módulo opencode_manager não disponível"}


@router.post("/api/opencode/headless/subagents")
def post_opencode_headless_subagents(req: Dict[str, Any] = Body(...)):
    mgr = _get_opencode_mgr()
    if mgr:
        subagent = mgr.register_subagent(
            parent_session_id=req.get("parent_session_id", req.get("session_id", "default")),
            subagent_id=req.get("subagent_id", req.get("id")), role=req.get("role", "builder"),
            task=req.get("task", ""), terminal_id=req.get("terminal_id"), stream_id=req.get("stream_id"),
            meta=req.get("meta"), broadcast_callback=manager.broadcast_sync
        )
        return {"status": "ok", "subagent": subagent}
    return {"status": "error", "message": "Módulo opencode_manager não disponível"}


@router.get("/api/opencode/headless/status")
def get_opencode_headless_status(session_id: Optional[str] = None):
    mgr = _get_opencode_mgr()
    if mgr:
        status_info = mgr.get_headless_status(session_id)
        return {"status": "ok", "data": status_info}
    return {"status": "error", "message": "Módulo opencode_manager não disponível"}
