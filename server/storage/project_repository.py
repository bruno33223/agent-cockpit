import json, os, re, hashlib, time, tempfile, threading
from contextlib import contextmanager
try:
    import fcntl
except ImportError:
    fcntl = None
from typing import List, Dict, Any, Optional
from .project_cleaner import (
    is_slice_identifier,
    validate_and_normalize_project_path,
    default_initial_state,
    purge_stale_or_temp_projects,
    verify_commit_proof,
    checkpoint_ops,
    scan_local_projects_impl
)

def normalize_canonical_path(path: str) -> str:
    abs_p = os.path.abspath(os.path.expanduser(path))
    match = re.match(r'^(.*?)[/\\]\.worktrees(?:[/\\]|$)', abs_p)
    return os.path.abspath(match.group(1)) if match else abs_p

def canonical_project_id(project_path_or_name: Optional[str]) -> str:
    if not project_path_or_name:
        return "default"
    val = project_path_or_name.strip()
    if is_slice_identifier(val):
        if ".worktrees" in val:
            abs_p = normalize_canonical_path(val)
            slug = re.sub(r'[^a-zA-Z0-9_\-]', '-', os.path.basename(abs_p) or "workspace").strip('-').lower() or "workspace"
            return f"{slug}-{hashlib.sha256(abs_p.encode('utf-8')).hexdigest()[:8]}"
        return "default"
    if val == "default" or bool(re.search(r'-[0-9a-f]{8}$', val)):
        return val
    abs_p = normalize_canonical_path(val)
    slug = re.sub(r'[^a-zA-Z0-9_\-]', '-', os.path.basename(abs_p) or "workspace").strip('-').lower() or "workspace"
    return f"{slug}-{hashlib.sha256(abs_p.encode('utf-8')).hexdigest()[:8]}"

class ProjectRepository:
    def __init__(self, states_dir: str, index_file: str, legacy_file: str, lock: Optional[threading.RLock] = None):
        self.states_dir, self.index_file, self.legacy_file = os.path.abspath(states_dir), os.path.abspath(index_file), os.path.abspath(legacy_file)
        self.lock = lock or threading.RLock()

    _local_locks = threading.local()

    @contextmanager
    def _file_lock(self, filepath: str):
        lock_path = os.path.realpath(filepath if filepath.endswith('.lock') else f"{filepath}.lock")
        if not hasattr(self._local_locks, "active"):
            self._local_locks.active = set()
        if lock_path in self._local_locks.active:
            yield
            return

        try: os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        except Exception: pass
        fd = None
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o666)
            if fcntl:
                try: fcntl.flock(fd, fcntl.LOCK_EX)
                except (OSError, IOError): pass
            self._local_locks.active.add(lock_path)
            yield
        finally:
            self._local_locks.active.discard(lock_path)
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
                if is_slice_identifier(pid):
                    continue
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

    def _is_production_dir(self) -> bool:
        prod = os.path.realpath(os.path.join(os.path.dirname(__file__), '..', '..', 'states'))
        return os.path.realpath(self.states_dir) == prod

    def _update_index_entry(self, project_id: str, project_name: str,
                            project_root: Optional[str], state_data: Dict[str, Any]):
        if is_slice_identifier(project_id):
            return
        if self._is_production_dir():
            tmp_dir = os.path.realpath(tempfile.gettempdir())
            if project_root:
                r_str = str(project_root)
                if r_str.startswith("/tmp") or os.path.realpath(r_str).startswith(tmp_dir):
                    return
                if not os.path.exists(project_root) and project_id != "default":
                    return
            elif project_id != "default" and project_id not in self._read_index().get("projects", {}):
                return

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
        display_name = project_name.strip() if project_name and project_name.strip() else (folder_name or "Projeto Sem Nome")
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
                if is_slice_identifier(pid):
                    continue
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
            if is_slice_identifier(val):
                if ".worktrees" in val:
                    return canonical_project_id(val)
                if project_root and not is_slice_identifier(project_root):
                    return canonical_project_id(project_root)
                return self.get_current_project_id()
            if val == "default":
                return "default"
            idx = self._read_index()
            if val in idx.get("projects", {}) or (os.path.exists(self._get_project_file(val)) and not is_slice_identifier(val)):
                return val
            if "/" not in val and "\\" not in val:
                return val
            return canonical_project_id(val)
        if project_root:
            if is_slice_identifier(project_root):
                if ".worktrees" in project_root:
                    return canonical_project_id(project_root)
                return self.get_current_project_id()
            return canonical_project_id(project_root)
        return self.get_current_project_id()

    def import_project(self, project_path: str, name: Optional[str] = None, switch: bool = True) -> Dict[str, Any]:
        with self.lock:
            canonical_path = validate_and_normalize_project_path(project_path)
            folder_name = os.path.basename(canonical_path) or "workspace"
            display_name = name.strip() if name and name.strip() else folder_name
            pid = canonical_project_id(canonical_path)
            pfile = self._get_project_file(pid)
            if not os.path.exists(pfile):
                state_data = default_initial_state(project_name=display_name, project_root=canonical_path)
                self._atomic_write_json(pfile, state_data)
            else:
                try:
                    with open(pfile, "r", encoding="utf-8") as f:
                        state_data = json.load(f)
                    state_data["project_root"] = canonical_path
                    if name and name.strip():
                        state_data.setdefault("epic", {})["name"] = display_name
                    self._atomic_write_json(pfile, state_data)
                except Exception:
                    state_data = default_initial_state(project_name=display_name, project_root=canonical_path)
                    self._atomic_write_json(pfile, state_data)
            self._update_index_entry(pid, display_name, canonical_path, state_data)
            if switch:
                self.switch_current_project(pid)
            proj_meta = self._read_index().get("projects", {}).get(pid, {
                "id": pid, "name": display_name, "project_root": canonical_path
            })
            return {"status": "ok", "project": proj_meta, "current_project_id": self.get_current_project_id()}

    def purge_stale_or_temp_projects(self) -> Dict[str, Any]:
        with self.lock:
            return purge_stale_or_temp_projects(
                self.states_dir, self.index_file, "default",
                self._atomic_write_json, self._file_lock
            )

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
        return scan_local_projects_impl(self, base_dir)

    def freeze_checkpoint(self, state: Dict[str, Any], project_id: str) -> str:
        with self.lock:
            return checkpoint_ops(self.states_dir, self._atomic_write_json, "freeze", project_id, state)

    def read_checkpoint(self, project_id: str) -> Optional[Dict[str, Any]]:
        return checkpoint_ops(self.states_dir, self._atomic_write_json, "read", project_id)

    def verify_worktree_commit_proof(self, repo_root: str, slice_id: str, base_branch: str = "master") -> Dict[str, Any]:
        return verify_commit_proof(repo_root, slice_id, base_branch)
