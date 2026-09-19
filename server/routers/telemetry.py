"""
telemetry.py: Endpoints de telemetria, ciclo de vida do workspace, grafo e estado do Agent Cockpit.
"""

import os
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from state_store import db
from fs_utils import _resolve_project_fs_root

router = APIRouter(tags=["telemetry"])


class SwitchProjectPayload(BaseModel):
    project_id: str


class ImportProjectPayload(BaseModel):
    path: str
    name: Optional[str] = None
    switch: Optional[bool] = True


class SteeringPayload(BaseModel):
    text: str
    project_id: Optional[str] = None
    slice_id: Optional[str] = None


class ResetPayload(BaseModel):
    project_id: Optional[str] = None


class ProjectRootPayload(BaseModel):
    path: str
    project_id: Optional[str] = None


# ROTAS DE GERENCIAMENTO DE PROJETOS / WORKSPACES

@router.get("/api/projects")
def get_projects():
    """Retorna lista de todos os workspaces conhecidos com metadados."""
    return {
        "current_project_id": db.get_current_project_id(),
        "projects": db.list_projects()
    }


@router.get("/api/projects/current")
def get_current_project():
    pid = db.get_current_project_id()
    return {"current_project_id": pid, "state": db.get_state(pid)}


@router.post("/api/projects/switch")
def post_switch_project(payload: SwitchProjectPayload):
    new_pid = db.switch_current_project(payload.project_id)
    return {
        "status": "ok",
        "current_project_id": new_pid,
        "projects": db.list_projects(),
        "state": db.get_state(new_pid)
    }


@router.delete("/api/projects/{project_id}")
def delete_project_endpoint(project_id: str):
    success = db.delete_project(project_id)
    return {"status": "ok" if success else "error", "projects": db.list_projects()}


@router.post("/api/projects/import")
def import_project_endpoint(payload: ImportProjectPayload):
    """Importa explicitamente um projeto existente a partir do diretório raiz local."""
    try:
        res = db.import_project(payload.path, name=payload.name, switch=(payload.switch is not False))
        return {
            "status": "ok",
            "project": res.get("project"),
            "current_project_id": res.get("current_project_id"),
            "projects": db.list_projects()
        }
    except (ValueError, FileNotFoundError, NotADirectoryError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao importar projeto: {e}")


@router.post("/api/projects/purge")
def purge_projects_endpoint():
    """Purga projetos fantasmas e arquivos órfãos de teste de states/."""
    report = db.purge_stale_or_temp_projects()
    return {
        "status": "ok",
        "report": report,
        "current_project_id": db.get_current_project_id(),
        "projects": db.list_projects()
    }


@router.get("/api/projects/scan")
@router.post("/api/projects/scan")
def scan_projects():
    """Descobre projetos reais em ~/Projects e atualiza a lista de workspaces."""
    projects = db.scan_local_projects()
    return {
        "status": "ok",
        "current_project_id": db.get_current_project_id(),
        "projects": projects
    }


# ROTAS DE ESTADO, HEALTH E TELEMETRIA

@router.get("/api/state")
def get_state(project_id: Optional[str] = None):
    return db.get_state(project_id)


@router.post("/api/steering")
def post_steering(payload: SteeringPayload):
    if not payload.text.strip():
        return {"error": "Texto não pode ser vazio"}
    msg = db.add_user_steering(payload.text.strip(), project_id=payload.project_id, slice_id=payload.slice_id)
    return {"status": "ok", "message": msg}


@router.get("/api/steering/messages")
def get_steering_messages(project_id: Optional[str] = None, slice_id: Optional[str] = None):
    messages = db.get_slice_steering_messages(project_id=project_id, slice_id=slice_id)
    return {"status": "ok", "messages": messages, "project_id": project_id, "slice_id": slice_id}


@router.post("/api/reset")
def post_reset(payload: Optional[ResetPayload] = None):
    pid = payload.project_id if payload else None
    state = db.reset_state(project_id=pid)
    return {"status": "ok", "state": state}


@router.get("/api/health")
def get_health():
    return {"status": "healthy", "service": "agent-cockpit"}


@router.get("/api/graph")
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


@router.post("/api/project_root")
def post_project_root(payload: ProjectRootPayload):
    p = payload.path.strip()
    if not os.path.exists(p):
        return {"status": "error", "message": f"Caminho não encontrado: {p}"}
    saved_p = db.set_project_root(p, project_id=payload.project_id)
    return {"status": "ok", "project_root": saved_p}


@router.get("/api/metrics")
def get_metrics(project_id: Optional[str] = None):
    return db.get_metrics(project_id)
