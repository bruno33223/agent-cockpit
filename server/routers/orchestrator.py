"""
orchestrator.py: Endpoints de orquestração, aprovação de gates, handoff, vault e file explorer.
"""

import os
import mimetypes
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from state_store import db
from connection_manager import manager
from fs_utils import _resolve_project_fs_root, DEFAULT_FS_IGNORE_DIRS, DEFAULT_FS_IGNORE_FILES

router = APIRouter(tags=["orchestrator"])


class GateApprovalPayload(BaseModel):
    gate: str = "gate_ship_approved"
    approved_by: str = "user"
    project_id: Optional[str] = None


class VaultNotePayload(BaseModel):
    file: str
    content: str
    root: Optional[str] = None
    project_id: Optional[str] = None


class ProjectRootPayload(BaseModel):
    path: str
    project_id: Optional[str] = None


@router.post("/api/gates/approve")
def post_approve_gate(payload: GateApprovalPayload):
    return db.approve_gate(payload.gate, payload.approved_by, project_id=payload.project_id)


@router.get("/api/handoff")
def get_handoff(root: Optional[str] = None, project_id: Optional[str] = None):
    import workflow_lock
    target_root = root or db.get_project_root(project_id) or "."
    data = workflow_lock.read_latest_handoff(target_root)
    if not data:
        return {"status": "NO_HANDOFF_FOUND", "content": "# Nenhum HANDOFF.md encontrado\nExecute a tool MCP `generate_handoff` na conclusão do Épico."}
    return data


@router.get("/api/vault/note")
def get_vault_note(file: str, root: Optional[str] = None, project_id: Optional[str] = None):
    from code_graph import get_file_vault_note
    if ".." in file or file.startswith("/") or file.startswith("\\"):
        raise HTTPException(status_code=403, detail="Acesso negado: tentativa de path traversal")
    target_root = root or db.get_project_root(project_id) or "."
    try:
        return get_file_vault_note(target_root, file)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/api/vault/note")
def post_vault_note(payload: VaultNotePayload):
    from code_graph import save_file_vault_note
    if ".." in payload.file or payload.file.startswith("/") or payload.file.startswith("\\"):
        raise HTTPException(status_code=403, detail="Acesso negado: tentativa de path traversal")
    target_root = payload.root or db.get_project_root(payload.project_id) or "."
    try:
        return save_file_vault_note(target_root, payload.file, payload.content)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/api/vault/sync")
def post_vault_sync(payload: Optional[ProjectRootPayload] = None):
    from code_graph import get_graph_elements_for_ui
    pid = payload.project_id if payload else None
    target_root = (payload and payload.path) or db.get_project_root(pid) or "."
    return get_graph_elements_for_ui(target_root)


@router.get("/api/fs/tree")
def get_fs_tree(project_id: Optional[str] = None, subpath: Optional[str] = "", max_depth: int = 4):
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

        dirs, files = [], []
        for entry in items:
            name = entry.name
            if name in DEFAULT_FS_IGNORE_DIRS or name in DEFAULT_FS_IGNORE_FILES or name.startswith(".env") or name == ".git":
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
            children = _build_tree(d.path, child_rel_norm, current_depth + 1) if current_depth < max_depth else []
            result.append({"name": d.name, "path": child_rel_norm, "type": "directory", "children": children})

        for f in files:
            child_rel = os.path.join(rel_prefix, f.name) if rel_prefix else f.name
            child_rel_norm = child_rel.replace("\\", "/")
            try:
                size = f.stat().st_size
            except OSError:
                size = 0
            result.append({"name": f.name, "path": child_rel_norm, "type": "file", "size": size})
        return result

    entries = _build_tree(target_dir, clean_subpath.replace("\\", "/"), 1)
    return {"root": root_path, "name": project_name, "project_id": target_pid, "subpath": clean_subpath.replace("\\", "/"), "entries": entries}


@router.get("/api/fs/read")
def read_fs_file(path: str, project_id: Optional[str] = None, max_bytes: int = 512 * 1024):
    if not isinstance(project_id, str):
        project_id = None
    if not isinstance(max_bytes, int):
        max_bytes = 512 * 1024

    root_path, _, _ = _resolve_project_fs_root(project_id)
    clean_p = (path or "").strip()
    if not clean_p:
        raise HTTPException(status_code=400, detail="Parâmetro 'path' é obrigatório.")

    if os.path.isabs(clean_p):
        target_file = os.path.abspath(clean_p)
        allowed_roots = [root_path] + [os.path.abspath(p.get("project_root")) for p in db.list_projects() if p.get("project_root") and os.path.exists(p.get("project_root"))]
        is_safe = any(os.path.commonpath([r, target_file]) == r for r in allowed_roots if os.path.exists(r))
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
    if file_name in DEFAULT_FS_IGNORE_FILES or file_name in DEFAULT_FS_IGNORE_DIRS or file_name.startswith(".env") or file_name == ".git":
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
            return {"path": rel_path, "name": file_name, "size": file_size, "is_binary": True, "content": "", "truncated": False, "mime": mime_type, "error": "Arquivo binário não suportado para visualização em texto."}
        try:
            text_content = chunk.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text_content = chunk.decode("latin-1")
            except Exception:
                return {"path": rel_path, "name": file_name, "size": file_size, "is_binary": True, "content": "", "truncated": False, "mime": mime_type, "error": "Codificação de arquivo não suportada para preview de texto."}
        return {"path": rel_path, "name": file_name, "size": file_size, "is_binary": False, "content": text_content, "truncated": file_size > max_bytes, "mime": mime_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler arquivo: {str(e)}")


def notify_worker_task_completion(task_data: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
    """Emite mensagem do orquestrador em linguagem natural quando um worker conclui tarefa."""
    slice_id = task_data.get("slice_id") or "geral"
    ticket_id = task_data.get("ticket_id") or "desconhecido"
    status = task_data.get("status")
    duration = task_data.get("duration", 0.0)
    tokens = task_data.get("tokens", 0)
    error = task_data.get("error")

    if status == "completed":
        text = (
            f"Fatia '{slice_id}' concluída com sucesso pelo Local Worker em {duration:.1f}s "
            f"({tokens} tokens gerados, Ticket: {ticket_id})."
        )
    else:
        text = (
            f"A execução da fatia '{slice_id}' falhou no Local Worker após {duration:.1f}s: "
            f"{error or 'Erro indeterminado'} (Ticket: {ticket_id})."
        )

    msg_dict = {
        "text": text,
        "project_id": project_id,
        "slice_id": slice_id,
        "sender": "ORCHESTRATOR"
    }
    if db and hasattr(db, "post_orchestrator_message"):
        res = db.post_orchestrator_message(
            text=text,
            project_id=project_id,
            slice_id=slice_id,
            sender="ORCHESTRATOR"
        )
        if isinstance(res, dict):
            msg_dict = res

    if manager:
        try:
            manager.broadcast_sync("ORCHESTRATOR_MESSAGE", msg_dict, project_id)
        except Exception:
            pass
    return msg_dict
