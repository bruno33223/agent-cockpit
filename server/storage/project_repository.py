import json, os, re, hashlib, time, tempfile, threading, subprocess
from contextlib import contextmanager
try:
    import fcntl
except ImportError:
    fcntl = None
from typing import List, Dict, Any, Optional

def normalize_canonical_path(path: str) -> str:
    abs_p = os.path.abspath(os.path.expanduser(path))
    match = re.match(r'^(.*?)[/\\]\.worktrees(?:[/\\]|$)', abs_p)
    return os.path.abspath(match.group(1)) if match else abs_p

def canonical_project_id(project_path_or_name: Optional[str]) -> str:
    if not project_path_or_name:
        return "default"
    val = project_path_or_name.strip()
    if re.match(r'^slice-\d+$', val):
        return "default"
    if ".worktrees" in val:
        abs_p = normalize_canonical_path(val)
        slug = re.sub(r'[^a-zA-Z0-9_\-]', '-', os.path.basename(abs_p) or "workspace").strip('-').lower() or "workspace"
        return f"{slug}-{hashlib.sha256(abs_p.encode('utf-8')).hexdigest()[:8]}"
    if val == "default" or bool(re.search(r'-[0-9a-f]{8}$', val)):
        return val
    abs_p = normalize_canonical_path(val)
    slug = re.sub(r'[^a-zA-Z0-9_\-]', '-', os.path.basename(abs_p) or "workspace").strip('-').lower() or "workspace"
    return f"{slug}-{hashlib.sha256(abs_p.encode('utf-8')).hexdigest()[:8]}"

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
        "human_gates": {"gate_plan_approved": True, "gate_ship_approved": False, "last_approved_at": None, "approved_by": None},
        "last_handoff": None,
        "local_worker": {"enabled": False, "provider": "ollama", "endpoint": "http://127.0.0.1:11434", "model": "deepseek-coder-v2:16b-q3_k_m", "circuit_breaker_threshold": 2, "consecutive_failures": {}, "auto_start_ollama": False, "delegate_styles_to_cloud": True},
        "governance_settings": {"autostart_slices": False, "security_preset": "standard", "human_gate_policy": "manual", "artifact_review_policy": "strict"},
        "project_settings_overrides": {}
    }

class ProjectRepository:
    def __init__(self, states_dir: str, index_file: str, legacy_file: str, lock: Optional[threading.RLock] = None):
        self.states_dir, self.index_file, self.legacy_file = os.path.abspath(states_dir), os.path.abspath(index_file), os.path.abspath(legacy_file)
        self.lock = lock or threading.RLock()

    @contextmanager
    def _file_lock(self, filepath: str):
        lock_path = filepath if filepath.endswith('.lock') else f"{filepath}.lock"
        try: os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
        except Exception: pass
        fd = None
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o666)
            if fcntl:
                try: fcntl.flock(fd, fcntl.LOCK_EX)
                except (OSError, IOError): pass
            yield
        finally:
            if fd is not None:
                if fcntl:
                    try: fcntl.flock(fd, fcntl.LOCK_UN)
                    except (OSError, IOError): pass
                try: os.close(fd)
                except Exception: pass

    def _atomic_write_json(self, filepath: str, data: Any):
        target_dir = os.path.dirname(os.path.abspath(filepath))
        os.makedirs(target_dir, exist_ok=True)
        with self._file_lock(filepath):
            temp_fd, temp_path = tempfile.mkstemp(dir=target_dir, prefix=".tmp_", suffix=".tmp")
            try:
                with open(temp_fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, filepath)
            except Exception:
                if os.path.exists(temp_path):
                    try: os.remove(temp_path)
                    except Exception: pass
                raise

    def _get_project_file(self, project_id: str) -> str:
        safe_id = re.sub(r'[^a-zA-Z0-9_\-]', '-', project_id) or "default"
        return os.path.join(self.states_dir, f"{safe_id}.json")

    def _read_index(self) -> Dict[str, Any]:
        if not os.path.exists(self.index_file):
            return {"current_project_id": "default", "projects": {}}
        try:
            with open(self.index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            projects, current_id = data.get("projects", {}), data.get("current_project_id", "default")
            seen_roots, cleaned, id_mapping = {}, {}, {}
            for pid, pmeta in list(projects.items()):
                p_root = pmeta.get("project_root")
                norm = os.path.realpath(os.path.abspath(p_root)) if p_root and os.path.exists(p_root) else p_root
                if norm:
                    if norm in seen_roots:
                        existing_pid = seen_roots[norm]
                        if pid == current_id:
                            id_mapping[existing_pid] = pid
                            cleaned[pid] = pmeta
                            cleaned.pop(existing_pid, None)
                            seen_roots[norm] = pid
                        else:
                            id_mapping[pid] = existing_pid
                        continue
                    seen_roots[norm] = pid
                cleaned[pid] = pmeta
            if len(cleaned) != len(projects):
                data["projects"] = cleaned
                if current_id in id_mapping:
                    data["current_project_id"] = id_mapping[current_id]
                self._save_index(data)
            return data
        except Exception:
            return {"current_project_id": "default", "projects": {}}

    def _save_index(self, index_data: Dict[str, Any]):
        self._atomic_write_json(self.index_file, index_data)

    def _update_index_entry(self, project_id: str, project_name: str,
                            project_root: Optional[str], state_data: Dict[str, Any]):
        nodes = state_data.get("nodes", [])
        approved = len([n for n in nodes if n.get("kanban_status") == "APPROVED"])
        active_pairs = len([p for p in state_data.get("pairs_3x3", []) if p.get("builder_status") in ("WORKING", "EXECUTING") or p.get("critic_status") in ("WORKING", "CRITIQUING")])
        active_nodes = len([n for n in nodes if n.get("kanban_status") in ("EXECUTING", "CRITIQUING", "WORKING")])
        waiting_user = bool(state_data.get("human_gate_pending") or any(n.get("kanban_status") in ("WAITING_REVIEW", "WAITING_USER", "HUMAN_GATE") for n in nodes))

        index_data = self._read_index()
        projects = index_data.setdefault("projects", {})
        norm = os.path.realpath(os.path.abspath(project_root)) if project_root and os.path.exists(project_root) else project_root

        if norm:
            for eid, meta in list(projects.items()):
                mr = meta.get("project_root")
                if mr and (os.path.realpath(os.path.abspath(mr)) if os.path.exists(mr) else mr) == norm and eid != project_id:
                    if index_data.get("current_project_id") == eid:
                        index_data["current_project_id"] = project_id
                    projects.pop(eid, None)
                    break

        folder_name = os.path.basename(norm) if norm else "Projeto Sem Nome"
        display_name = folder_name if folder_name else (project_name or "Projeto Sem Nome")
        projects[project_id] = {
            "id": project_id, "name": display_name, "project_root": norm or project_root,
            "epic_name": state_data.get("epic", {}).get("name", "Épico"),
            "epic_status": state_data.get("epic", {}).get("status", "PLANNING"),
            "total_slices": len(nodes), "approved_slices": approved,
            "active_agents": max(active_pairs, active_nodes), "waiting_user": waiting_user,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self._save_index(index_data)

    def get_current_project_id(self) -> str:
        with self.lock: return self._read_index().get("current_project_id", "default")

    def switch_current_project(self, project_id: str) -> str:
        target_pid = self.resolve_project_id(project_id) if project_id else self.get_current_project_id()
        with self.lock:
            index_data = self._read_index()
            index_data["current_project_id"] = target_pid
            self._save_index(index_data)
            return target_pid

    def list_projects(self) -> List[Dict[str, Any]]:
        with self.lock:
            index_data = self._read_index()
            curr, result = index_data.get("current_project_id", "default"), []
            for pid, pmeta in index_data.get("projects", {}).items():
                m = dict(pmeta)
                m["is_current"] = (pid == curr)
                m.setdefault("active_agents", 0)
                m.setdefault("waiting_user", False)
                result.append(m)
            result.sort(key=lambda x: (not x.get("is_current", False), x.get("updated_at", "")), reverse=True)
            return result

    def resolve_project_id(self, project_id: Optional[str] = None, project_root: Optional[str] = None) -> str:
        if project_id:
            val = project_id.strip()
            if re.match(r'^slice-\d+$', val):
                return self.get_current_project_id()
            if ".worktrees" in val:
                return canonical_project_id(val)
            idx = self._read_index()
            if val in idx.get("projects", {}) or os.path.exists(self._get_project_file(val)):
                return val
            if "/" not in val and "\\" not in val:
                return val
            return canonical_project_id(val)
        return canonical_project_id(project_root) if project_root else self.get_current_project_id()

    def delete_project(self, project_id: str) -> bool:
        with self.lock:
            idx = self._read_index()
            projects = idx.get("projects", {})
            if project_id in projects:
                del projects[project_id]
                if idx.get("current_project_id") == project_id:
                    idx["current_project_id"] = next(iter(projects.keys())) if projects else "default"
                self._save_index(idx)
            pfile = self._get_project_file(project_id)
            if os.path.exists(pfile):
                try: os.remove(pfile)
                except Exception: pass
            return True

    def scan_local_projects(self, base_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        target_dir = os.path.abspath(os.path.expanduser(base_dir or "~/Projects"))
        if not os.path.exists(target_dir):
            return self.list_projects()
        with self.lock:
            idx = self._read_index()
            projects = idx.setdefault("projects", {})
            existing = {p.get("project_root") for p in projects.values() if p.get("project_root")}
            for entry in os.scandir(target_dir):
                if not entry.is_dir() or entry.name.startswith(".") or entry.path in existing:
                    continue
                pid = canonical_project_id(entry.path)
                pfile = self._get_project_file(pid)
                if not os.path.exists(pfile):
                    init_st = default_initial_state(project_name=entry.name, project_root=entry.path)
                    self._atomic_write_json(pfile, init_st)
                    self._update_index_entry(pid, entry.name, entry.path, init_st)
                elif pid not in projects:
                    try:
                        with open(pfile, 'r', encoding='utf-8') as f:
                            s_data = json.load(f)
                    except Exception:
                        s_data = default_initial_state(project_name=entry.name, project_root=entry.path)
                    self._update_index_entry(pid, entry.name, entry.path, s_data)
        return self.list_projects()

    def freeze_checkpoint(self, state: Dict[str, Any], project_id: str) -> str:
        with self.lock:
            cp_file = os.path.join(self.states_dir, f"{re.sub(r'[^a-zA-Z0-9_-]', '-', project_id) or 'default'}.checkpoint.json")
            self._atomic_write_json(cp_file, {
                "checkpoint_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "project_id": project_id, "project_root": state.get("project_root"),
                "epic": state.get("epic"), "nodes": state.get("nodes"),
                "pairs_3x3": state.get("pairs_3x3"), "human_gates": state.get("human_gates")
            })
            return cp_file

    def read_checkpoint(self, project_id: str) -> Optional[Dict[str, Any]]:
        cp_file = os.path.join(self.states_dir, f"{re.sub(r'[^a-zA-Z0-9_-]', '-', project_id) or 'default'}.checkpoint.json")
        if not os.path.exists(cp_file):
            return None
        try:
            with open(cp_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def verify_worktree_commit_proof(self, repo_root: str, slice_id: str, base_branch: str = "master") -> Dict[str, Any]:
        root, branch = os.path.abspath(os.path.expanduser(repo_root)), f"cockpit/{slice_id}"
        res = subprocess.run(["git", "-C", root, "rev-parse", "--verify", branch], capture_output=True, text=True, check=False)
        if res.returncode != 0:
            return {"valid_proof": False, "reason": f"Branch '{branch}' não encontrada no repositório. O subagente não comitou nada.", "commits_count": 0}
        b_head = res.stdout.strip()
        res_b = subprocess.run(["git", "-C", root, "rev-parse", "--verify", base_branch], capture_output=True, text=True, check=False)
        if b_head == (res_b.stdout.strip() if res_b.returncode == 0 else ""):
            return {"valid_proof": False, "reason": f"A branch '{branch}' aponta exatamente para a '{base_branch}'. Nenhum commit de trabalho foi produzido.", "commits_count": 0}
        log = subprocess.run(["git", "-C", root, "log", f"{base_branch}..{branch}", "--oneline"], capture_output=True, text=True, check=False)
        lines = [l.strip() for l in log.stdout.splitlines() if l.strip()]
        return {"valid_proof": len(lines) > 0, "head_commit": b_head, "commits_count": len(lines), "commits": lines, "latest_commit_msg": lines[0] if lines else ""}
