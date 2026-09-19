"""
fs_utils.py: Utilitários para navegação segura de sistema de arquivos e resolução de raízes de workspaces.
"""

import os
from typing import Optional, Tuple
from state_store import db

DEFAULT_FS_IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "dist", "build", ".next", ".nuxt",
    ".output", ".turbo", ".cache", ".idea", ".vscode"
}

DEFAULT_FS_IGNORE_FILES = {
    ".git", ".DS_Store", "Thumbs.db", ".env", ".env.local"
}


def _resolve_project_fs_root(project_id: Optional[str] = None) -> Tuple[str, str, str]:
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
