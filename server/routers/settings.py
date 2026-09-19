"""
settings.py: Endpoints de configurações globais, governança, autostart, customizações e workspaces.
"""

from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from state_store import db
from connection_manager import manager

try:
    from customizations_manager import CustomizationsManager
except ImportError:
    try:
        from server.customizations_manager import CustomizationsManager
    except ImportError:
        CustomizationsManager = None

router = APIRouter(tags=["settings"])
_customizations_mgr_instance = None


def get_customizations_mgr() -> Any:
    global _customizations_mgr_instance
    if _customizations_mgr_instance is None and CustomizationsManager:
        _customizations_mgr_instance = CustomizationsManager()
    return _customizations_mgr_instance


def set_customizations_mgr(mgr: Any):
    global _customizations_mgr_instance
    _customizations_mgr_instance = mgr


def _call_mgr(method_names: List[str], *args, **kwargs):
    mgr = get_customizations_mgr()
    method = next((getattr(mgr, m) for m in method_names if callable(getattr(mgr, m, None))), None)
    if not method:
        raise HTTPException(status_code=500, detail="Método de customização não disponível no manager.")
    try:
        return method(*args, **kwargs)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# MODELOS PYDANTIC
class AutostartPayload(BaseModel):
    enabled: bool

class SettingsPayload(BaseModel):
    enable_local_ai: Optional[bool] = None
    delegate_styles_to_cloud: Optional[bool] = None
    model: Optional[str] = None
    auto_start_ollama: Optional[bool] = None
    circuit_breaker_threshold: Optional[int] = None
    project_root: Optional[str] = None
    project_id: Optional[str] = None

class GovernancePayload(BaseModel):
    autostart_slices: Optional[bool] = None
    security_preset: Optional[str] = None
    human_gate_policy: Optional[str] = None
    artifact_review_policy: Optional[str] = None
    project_id: Optional[str] = None

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


# ROTAS AUTOSTART & SETTINGS & GOVERNANCE
@router.get("/api/autostart")
def get_autostart_status():
    from autostart import get_autostart_info
    return get_autostart_info()

@router.post("/api/autostart")
def post_autostart_toggle(payload: AutostartPayload):
    from autostart import enable_autostart, disable_autostart, get_autostart_info
    success = enable_autostart() if payload.enabled else disable_autostart()
    info = get_autostart_info()
    info["success"] = success
    return info

@router.get("/api/settings")
def get_settings_endpoint(project_id: Optional[str] = None):
    return db.get_settings(project_id=project_id)

@router.post("/api/settings")
def post_settings_endpoint(payload: SettingsPayload):
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    updates = {k: v for k, v in data.items() if v is not None and k != "project_id"}
    return db.update_settings(updates, project_id=payload.project_id)

@router.get("/api/governance")
def get_governance_endpoint(project_id: Optional[str] = None):
    return db.get_governance_settings(project_id=project_id)

@router.post("/api/governance")
def post_governance_endpoint(payload: GovernancePayload):
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    updates = {k: v for k, v in data.items() if v is not None and k != "project_id"}
    res = db.update_governance_settings(updates, project_id=payload.project_id)
    manager.broadcast_sync("GOVERNANCE_SETTINGS_UPDATED", res)
    return res


# ROTAS DE CUSTOMIZAÇÕES (MCP E SKILLS)
@router.get("/api/customizations/mcp")
def get_customizations_mcp():
    mgr = get_customizations_mgr()
    m = getattr(mgr, "list_mcp_servers", getattr(mgr, "list_mcps", None))
    servers = m() if callable(m) else []
    return {"status": "success", "mcp_servers": servers, "count": len(servers)}

@router.post("/api/customizations/mcp")
def post_customizations_mcp(payload: MCPServerPayload):
    mcp_id = (payload.id or payload.name or "").strip()
    if not mcp_id:
        raise HTTPException(status_code=400, detail="ID ou nome do servidor MCP é obrigatório.")
    mcp_type = (payload.type or "").strip().lower()
    if mcp_type == "stdio" and not (payload.command and payload.command.strip()):
        raise HTTPException(status_code=400, detail="Comando é obrigatório para MCP do tipo stdio.")
    if mcp_type in ("sse", "http") and not (payload.url and payload.url.strip()):
        raise HTTPException(status_code=400, detail="URL é obrigatória para MCP do tipo sse/http.")

    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    data["id"] = mcp_id
    res = _call_mgr(["create_mcp_server", "add_mcp_server", "create_mcp"], data)
    manager.broadcast_sync("CUSTOMIZATIONS_MCP_UPDATED", {"action": "create", "mcp": res})
    return {"status": "success", "mcp_server": res, "message": f"Servidor MCP '{mcp_id}' criado com sucesso."}

@router.put("/api/customizations/mcp/{mcp_id}")
def put_customizations_mcp(mcp_id: str, payload: MCPServerUpdatePayload):
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    res = _call_mgr(["update_mcp_server", "update_mcp"], mcp_id, data)
    if res is None:
        raise HTTPException(status_code=404, detail=f"Servidor MCP '{mcp_id}' não encontrado.")
    manager.broadcast_sync("CUSTOMIZATIONS_MCP_UPDATED", {"action": "update", "mcp": res})
    return {"status": "success", "mcp_server": res, "message": f"Servidor MCP '{mcp_id}' atualizado com sucesso."}

@router.delete("/api/customizations/mcp/{mcp_id}")
def delete_customizations_mcp(mcp_id: str):
    deleted = _call_mgr(["delete_mcp_server", "delete_mcp"], mcp_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Servidor MCP '{mcp_id}' não encontrado.")
    manager.broadcast_sync("CUSTOMIZATIONS_MCP_UPDATED", {"action": "delete", "mcp_id": mcp_id})
    return {"status": "success", "message": f"Servidor MCP '{mcp_id}' excluído com sucesso."}

@router.post("/api/customizations/mcp/{mcp_id}/toggle")
def toggle_customizations_mcp(mcp_id: str, payload: Optional[MCPTogglePayload] = None):
    res = _call_mgr(["toggle_mcp_server", "toggle_mcp"], mcp_id, enabled=payload.enabled if payload else None)
    if res is None:
        raise HTTPException(status_code=404, detail=f"Servidor MCP '{mcp_id}' não encontrado.")
    manager.broadcast_sync("CUSTOMIZATIONS_MCP_UPDATED", {"action": "toggle", "mcp": res})
    return {"status": "success", "mcp_id": mcp_id, "enabled": res.get("enabled", False), "mcp_server": res,
            "message": f"Servidor MCP '{mcp_id}' {'ativado' if res.get('enabled') else 'desativado'} com sucesso."}

@router.get("/api/customizations/skills")
def get_customizations_skills():
    mgr = get_customizations_mgr()
    m = getattr(mgr, "list_skills", None)
    skills = m() if callable(m) else []
    return {"status": "success", "skills": skills, "count": len(skills)}

@router.post("/api/customizations/skills")
def post_customizations_skills(payload: SkillPayload):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome da skill é obrigatório.")
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    data["name"] = name
    res = _call_mgr(["create_skill", "add_skill"], data)
    manager.broadcast_sync("CUSTOMIZATIONS_SKILLS_UPDATED", {"action": "create", "skill": res})
    return {"status": "success", "skill": res, "message": f"Skill '{name}' criada com sucesso."}

@router.put("/api/customizations/skills/{skill_name}")
def put_customizations_skills(skill_name: str, payload: SkillUpdatePayload):
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    res = _call_mgr(["update_skill"], skill_name, data)
    if res is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' não encontrada.")
    manager.broadcast_sync("CUSTOMIZATIONS_SKILLS_UPDATED", {"action": "update", "skill": res})
    return {"status": "success", "skill": res, "message": f"Skill '{skill_name}' atualizada com sucesso."}

@router.delete("/api/customizations/skills/{skill_name}")
def delete_customizations_skills(skill_name: str):
    deleted = _call_mgr(["delete_skill"], skill_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' não encontrada.")
    manager.broadcast_sync("CUSTOMIZATIONS_SKILLS_UPDATED", {"action": "delete", "skill_name": skill_name})
    return {"status": "success", "message": f"Skill '{skill_name}' excluída com sucesso."}

@router.post("/api/customizations/skills/{skill_name}/toggle")
def toggle_customizations_skills(skill_name: str, payload: Optional[SkillTogglePayload] = None):
    res = _call_mgr(["toggle_skill"], skill_name, enabled=payload.enabled if payload else None)
    if res is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' não encontrada.")
    manager.broadcast_sync("CUSTOMIZATIONS_SKILLS_UPDATED", {"action": "toggle", "skill": res})
    return {"status": "success", "name": skill_name, "enabled": res.get("enabled", False), "skill": res,
            "message": f"Skill '{skill_name}' {'ativada' if res.get('enabled') else 'desativada'} com sucesso."}

@router.post("/api/customizations/sync")
def post_customizations_sync():
    mgr = get_customizations_mgr()
    sync_result = {}
    if hasattr(mgr, "sync_all"):
        sync_result = mgr.sync_all()
    elif hasattr(mgr, "sync"):
        sync_result = mgr.sync()
    else:
        sync_result = {"mcp_synced": True, "skills_synced": True}
    manager.broadcast_sync("CUSTOMIZATIONS_SYNCED", sync_result)
    return {"status": "success", "synced": True, "result": sync_result, "message": "Customizações sincronizadas com sucesso."}


# ROTAS DE CONFIGURAÇÃO POR PROJETO
@router.get("/api/projects/{project_id}/settings")
def get_project_settings_endpoint(project_id: str):
    try:
        return db.get_project_settings(project_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/api/projects/{project_id}/settings")
@router.post("/api/projects/{project_id}/settings")
def update_project_settings_endpoint(project_id: str, payload: Dict[str, Any]):
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

@router.delete("/api/projects/{project_id}/settings/overrides")
def clear_project_settings_overrides_endpoint(project_id: str):
    try:
        res = db.clear_project_settings_overrides(project_id)
        manager.broadcast_sync("PROJECT_SETTINGS_UPDATED", res, project_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
