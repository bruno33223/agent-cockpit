import os
import re
import json
import time
import tempfile
import subprocess
from typing import Dict, Any, List, Optional, Callable


def is_slice_identifier(identifier: Optional[str]) -> bool:
    """Verifica se um ID ou caminho representa uma fatia vertical ou worktree interna."""
    if not identifier:
        return False
    val = str(identifier).strip()
    if ".worktrees" in val or "/.worktrees" in val or "\\.worktrees" in val:
        return True
    if re.match(r"^slice(?:-[a-zA-Z0-9_\-]+)?$", val, re.IGNORECASE):
        return True
    return False


def validate_and_normalize_project_path(project_path: str) -> str:
    """Valida que o caminho existe, é diretório e não é uma pasta interna de fatia."""
    if not project_path or not str(project_path).strip():
        raise ValueError("O caminho do projeto não pode ser vazio.")
    expanded = os.path.expanduser(str(project_path).strip())
    canonical_path = os.path.realpath(os.path.abspath(expanded))
    if not os.path.exists(canonical_path):
        raise FileNotFoundError(f"Diretório do projeto não encontrado: '{canonical_path}'.")
    if not os.path.isdir(canonical_path):
        raise NotADirectoryError(f"O caminho informado não é um diretório: '{canonical_path}'.")
    if ".worktrees" in canonical_path:
        match = re.match(r"^(.*?)[/\\]\.worktrees(?:[/\\]|$)", canonical_path)
        if match:
            canonical_path = os.path.realpath(os.path.abspath(match.group(1)))
    return canonical_path


def default_initial_state(project_name: Optional[str] = None, project_root: Optional[str] = None) -> Dict[str, Any]:
    titles = [
        ("slice-1", "Fatia Vertical 1: Contratos & Dados", "- Contratos de interface validados\n- Zero acoplamento destrutivo\n- Testes de ponta a ponta"),
        ("slice-2", "Fatia Vertical 2: Regras & Domínio", "- Lógica de negócio coesa\n- Sem regressões funcionais"),
        ("slice-3", "Fatia Vertical 3: Interface & Integração", "- Renderização e usabilidade validadas\n- Auditoria de integração final aprovada"),
    ]
    nodes = [{
        "id": sid, "title": title, "pair_id": i + 1, "kanban_status": "BACKLOG", "attempt": 1, "max_attempts": 5,
        "acceptance_criteria": crit, "spec_md": f"### {title}\nAguardando envio do Master Blueprint pelo Orquestrador.",
        "latest_feedback": "Nenhuma revisão executada ainda.", "tdd_stage": "PENDING",
        "review_metrics": {"critical": 0, "important": 0, "minor": 0}, "updated_at": time.strftime("%H:%M:%S")
    } for i, (sid, title, crit) in enumerate(titles)]
    pair_names = ["Par 1: Infra & Contratos", "Par 2: Backend & Regras", "Par 3: Frontend & UX"]
    pairs_3x3 = [{
        "id": i + 1, "name": name, "builder_status": "IDLE", "critic_status": "IDLE",
        "current_slice_id": f"slice-{i+1}", "last_heartbeat": time.strftime("%H:%M:%S")
    } for i, name in enumerate(pair_names)]
    return {
        "epic": {"name": project_name or "Aguardando Inicialização do Épico", "goal": "Conecte o Antigravity via MCP para sincronizar o Master Blueprint.", "status": "PLANNING", "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")},
        "nodes": nodes, "pairs_3x3": pairs_3x3, "project_root": project_root,
        "steering_messages": [{"id": "msg-0", "sender": "ORCHESTRATOR", "text": "Agent Cockpit online. Conecte o Antigravity via MCP para iniciar o fluxo Spec-Driven.", "timestamp": time.strftime("%H:%M:%S"), "consumed": True}],
        "gauntlet_log": [],
        "human_gates": {"gate_plan_approved": False, "gate_ship_approved": False, "last_approved_at": None, "approved_by": None},
        "last_handoff": None,
        "local_worker": {"enabled": False, "provider": "ollama", "endpoint": "http://127.0.0.1:11434", "model": "deepseek-coder-v2:16b-q3_k_m", "circuit_breaker_threshold": 2, "consecutive_failures": {}, "auto_start_ollama": False, "delegate_styles_to_cloud": True},
        "governance_settings": {"autostart_slices": False, "security_preset": "standard", "human_gate_policy": "manual", "artifact_review_policy": "strict"},
        "project_settings_overrides": {}
    }


def purge_stale_or_temp_projects(
    states_dir: str,
    index_file: str,
    current_pid: str,
    atomic_write_fn: Callable[[str, Any], None],
    file_lock_cm: Callable[[str], Any]
) -> Dict[str, Any]:
    purged_projects: List[str] = []
    removed_files: List[str] = []
    tmp_prefix = os.path.realpath(tempfile.gettempdir())

    with file_lock_cm(index_file):
        index_data = {"current_project_id": "default", "projects": {}}
        if os.path.exists(index_file):
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    index_data = json.load(f)
            except Exception:
                pass

        projects = index_data.get("projects", {})
        cleaned_projects: Dict[str, Any] = {}

        active_test_env = os.path.dirname(os.path.realpath(states_dir)) if states_dir else None

        for pid, meta in list(projects.items()):
            root = meta.get("project_root")
            is_slice = is_slice_identifier(pid)
            root_real = os.path.realpath(str(root)) if root else ""
            in_tmp = bool(root and (str(root).startswith("/tmp") or root_real.startswith(tmp_prefix)))
            is_own_test_repo = bool(active_test_env and root_real.startswith(active_test_env) and os.path.exists(root_real))
            is_stale_tmp = in_tmp and not is_own_test_repo
            not_exists = bool(not root or not os.path.exists(root))

            if is_slice or is_stale_tmp or not_exists:
                purged_projects.append(pid)
            else:
                cleaned_projects[pid] = meta

        new_curr = index_data.get("current_project_id", "default")
        if new_curr in purged_projects or is_slice_identifier(new_curr) or (cleaned_projects and new_curr not in cleaned_projects):
            new_curr = next(iter(cleaned_projects.keys())) if cleaned_projects else "default"

        index_data["current_project_id"] = new_curr
        index_data["projects"] = cleaned_projects
        atomic_write_fn(index_file, index_data)

    if os.path.exists(states_dir):
        system_files = {"projects_index.json", "default.json", "worker_queue.json", ".gitkeep"}
        for fname in os.listdir(states_dir):
            fpath = os.path.join(states_dir, fname)
            if not os.path.isfile(fpath) or fname in system_files:
                continue
            if fname.startswith("slice-"):
                try:
                    os.remove(fpath)
                    removed_files.append(fname)
                except Exception:
                    pass
            for pid in purged_projects:
                safe_pid = re.sub(r"[^a-zA-Z0-9_\-]", "-", pid)
                if fname in (f"{safe_pid}.json", f"{safe_pid}.json.lock", f"{safe_pid}.checkpoint.json"):
                    try:
                        os.remove(fpath)
                        removed_files.append(fname)
                    except Exception:
                        pass
            if fname.endswith(".lock"):
                target_base = fname[:-5]
                if not os.path.exists(os.path.join(states_dir, target_base)):
                    try:
                        os.remove(fpath)
                        removed_files.append(fname)
                    except Exception:
                        pass
            elif fname.endswith(".json") and not fname.endswith(".checkpoint.json"):
                base_name = fname[:-5]
                if base_name not in cleaned_projects and base_name not in system_files:
                    try:
                        with open(fpath, "r", encoding="utf-8") as jf:
                            fdata = json.load(jf)
                        f_root = str(fdata.get("project_root", ""))
                        if f_root.startswith("/tmp") or (f_root and not os.path.exists(f_root)):
                            os.remove(fpath)
                            removed_files.append(fname)
                    except Exception:
                        pass

    return {
        "status": "ok", "purged_projects": purged_projects, "removed_files": removed_files,
        "remaining_projects_count": len(cleaned_projects), "current_project_id": new_curr
    }


def detect_base_branch(repo_root: str) -> str:
    """Detecta dinamicamente a branch base do repositório (origin/HEAD, main, master ou branch atual)."""
    root = os.path.abspath(os.path.expanduser(repo_root))
    if not os.path.isdir(root):
        return "main"
    res_sym = subprocess.run(["git", "-C", root, "symbolic-ref", "refs/remotes/origin/HEAD"], capture_output=True, text=True, check=False)
    if res_sym.returncode == 0 and res_sym.stdout.strip():
        branch = res_sym.stdout.strip().split("/")[-1].strip()
        if branch:
            return branch
    for candidate in ("main", "master"):
        if subprocess.run(["git", "-C", root, "rev-parse", "--verify", candidate], capture_output=True, text=True, check=False).returncode == 0:
            return candidate
    res_curr = subprocess.run(["git", "-C", root, "branch", "--show-current"], capture_output=True, text=True, check=False)
    curr = res_curr.stdout.strip() if res_curr.returncode == 0 else ""
    if curr:
        return curr
    return "HEAD" if subprocess.run(["git", "-C", root, "rev-parse", "--verify", "HEAD"], capture_output=True, text=True, check=False).returncode == 0 else "main"


def verify_commit_proof(repo_root: str, slice_id: str, base_branch: Optional[str] = None) -> Dict[str, Any]:
    root, branch = os.path.abspath(os.path.expanduser(repo_root)), f"cockpit/{slice_id}"
    target_base = base_branch
    if target_base and subprocess.run(["git", "-C", root, "rev-parse", "--verify", target_base], capture_output=True, text=True, check=False).returncode != 0:
        target_base = None
    if not target_base:
        target_base = detect_base_branch(root)
    res = subprocess.run(["git", "-C", root, "rev-parse", "--verify", branch], capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return {"valid_proof": False, "reason": f"Branch '{branch}' não encontrada no repositório. O subagente não comitou nada.", "commits_count": 0}
    b_head = res.stdout.strip()
    res_b = subprocess.run(["git", "-C", root, "rev-parse", "--verify", target_base], capture_output=True, text=True, check=False)
    if b_head == (res_b.stdout.strip() if res_b.returncode == 0 else ""):
        return {"valid_proof": False, "reason": f"A branch '{branch}' aponta exatamente para a '{target_base}'. Nenhum commit de trabalho foi produzido.", "commits_count": 0}
    log = subprocess.run(["git", "-C", root, "log", f"{target_base}..{branch}", "--oneline"], capture_output=True, text=True, check=False)
    lines = [l.strip() for l in log.stdout.splitlines() if l.strip()]
    return {"valid_proof": len(lines) > 0, "head_commit": b_head, "commits_count": len(lines), "commits": lines, "latest_commit_msg": lines[0] if lines else ""}



def checkpoint_ops(states_dir: str, atomic_write_fn: Callable, action: str, project_id: str, state: Optional[Dict[str, Any]] = None) -> Any:
    safe_pid = re.sub(r'[^a-zA-Z0-9_-]', '-', project_id) or 'default'
    cp_file = os.path.join(states_dir, f"{safe_pid}.checkpoint.json")
    if action == "freeze" and state is not None:
        atomic_write_fn(cp_file, {
            "checkpoint_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "project_id": project_id, "project_root": state.get("project_root"),
            "epic": state.get("epic"), "nodes": state.get("nodes"),
            "pairs_3x3": state.get("pairs_3x3"), "human_gates": state.get("human_gates")
        })
        return cp_file
    elif action == "read":
        if not os.path.exists(cp_file):
            return None
        try:
            with open(cp_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None


def scan_local_projects_impl(repo: Any, base_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    target_dir = os.path.abspath(os.path.expanduser(base_dir or "~/Projects"))
    if not os.path.exists(target_dir):
        return repo.list_projects()
    with repo.lock:
        idx = repo._read_index()
        projects = idx.setdefault("projects", {})
        existing = {p.get("project_root") for p in projects.values() if p.get("project_root")}
        for entry in os.scandir(target_dir):
            if not entry.is_dir() or entry.name.startswith(".") or entry.path in existing:
                continue
            from .project_repository import canonical_project_id
            pid = canonical_project_id(entry.path)
            pfile = repo._get_project_file(pid)
            if not os.path.exists(pfile):
                init_st = default_initial_state(project_name=entry.name, project_root=entry.path)
                repo._atomic_write_json(pfile, init_st)
                repo._update_index_entry(pid, entry.name, entry.path, init_st)
            elif pid not in projects:
                try:
                    with open(pfile, 'r', encoding='utf-8') as f:
                        s_data = json.load(f)
                except Exception:
                    s_data = default_initial_state(project_name=entry.name, project_root=entry.path)
                repo._update_index_entry(pid, entry.name, entry.path, s_data)
    return repo.list_projects()
