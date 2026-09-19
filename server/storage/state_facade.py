import os
import sys
import json
import time
import inspect
import threading
from typing import List, Dict, Any, Optional, Callable

from .project_repository import ProjectRepository, default_initial_state, canonical_project_id
from .slice_repository import SliceRepository
from .settings_repository import SettingsRepository

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
STATES_DIR = os.getenv("COCKPIT_STATES_DIR") or os.path.join(BASE_DIR, 'states')
LEGACY_STATE_FILE = os.getenv("COCKPIT_LEGACY_FILE") or os.path.join(BASE_DIR, 'workflow_state.json')

class StateFacade:
    """Fachada integradora de persistência compatível com a API do StateStore."""
    def __init__(self, states_dir: Optional[str] = None):
        env_dir = os.getenv("COCKPIT_STATES_DIR")
        self.states_dir = os.path.abspath(states_dir or env_dir or os.path.join(BASE_DIR, 'states'))
        self.index_file = os.path.join(self.states_dir, 'projects_index.json')
        self.legacy_file = os.getenv("COCKPIT_LEGACY_FILE") or (LEGACY_STATE_FILE if states_dir is None else os.path.join(self.states_dir, 'workflow_state.json'))
        self.lock = threading.RLock()
        self.listeners: List[Callable] = []

        self.project_repo = ProjectRepository(self.states_dir, self.index_file, self.legacy_file, self.lock)
        self.slice_repo = SliceRepository(self)
        self.settings_repo = SettingsRepository(self)
        self._ensure_init()

    def register_listener(self, callback: Callable): self.listeners.append(callback)

    def _notify(self, event_type: str, payload: Any, project_id: Optional[str] = None):
        target_pid = project_id or self.get_current_project_id()
        for listener in self.listeners:
            try:
                sig = inspect.signature(listener)
                if len(sig.parameters) >= 3:
                    listener(event_type, payload, target_pid)
                else:
                    listener(event_type, payload)
            except Exception as e:
                print(f"[StateFacade] Erro notificando listener: {e}", file=sys.stderr)

    def _file_lock(self, filepath: str): return self.project_repo._file_lock(filepath)
    def _atomic_write_json(self, filepath: str, data: Any): return self.project_repo._atomic_write_json(filepath, data)
    def _get_project_file(self, project_id: str) -> str: return self.project_repo._get_project_file(project_id)
    def _read_index(self) -> Dict[str, Any]: return self.project_repo._read_index()
    def _save_index(self, index_data: Dict[str, Any]): self.project_repo._save_index(index_data)
    def _update_index_entry(self, project_id: str, project_name: str, project_root: Optional[str], state_data: Dict[str, Any]):
        self.project_repo._update_index_entry(project_id, project_name, project_root, state_data)

    def _ensure_init(self):
        with self.lock:
            os.makedirs(self.states_dir, exist_ok=True)
            if not os.path.exists(self.index_file):
                self.project_repo._save_index({"current_project_id": "default", "projects": {}})
            default_file = self._get_project_file("default")
            if os.path.exists(self.legacy_file) and not os.path.exists(default_file):
                try:
                    with open(self.legacy_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self._atomic_write_json(default_file, data)
                    self.project_repo._update_index_entry("default", data.get("epic", {}).get("name", "Default Project"), data.get("project_root"), data)
                except Exception as e:
                    print(f"[StateFacade] Falha ao migrar legado: {e}", file=sys.stderr)
            if not os.path.exists(default_file):
                init_data = default_initial_state("Projeto Padrão")
                self._atomic_write_json(default_file, init_data)
                self.project_repo._update_index_entry("default", "Projeto Padrão", None, init_data)

    def get_state(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id) if project_id else self.get_current_project_id()
        pfile = self._get_project_file(target_pid)
        with self.lock:
            if not os.path.exists(pfile):
                state = default_initial_state("Projeto Padrão")
            else:
                try:
                    with open(pfile, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                except Exception:
                    state = default_initial_state("Projeto Padrão")
            if not state.get("pairs_3x3"):
                state["pairs_3x3"] = default_initial_state().get("pairs_3x3", [])
            state["project_id"] = target_pid
            state["active_project_id"] = target_pid
            if not state.get("project_root"):
                pmeta = self.project_repo._read_index().get("projects", {}).get(target_pid, {})
                if pmeta.get("project_root"):
                    state["project_root"] = pmeta.get("project_root")
            return state

    def _save_state(self, state: Dict[str, Any], project_id: str):
        target_pid = self.resolve_project_id(project_id)
        self._atomic_write_json(self._get_project_file(target_pid), state)
        existing_name = self.project_repo._read_index().get("projects", {}).get(target_pid, {}).get("name")
        folder_name = os.path.basename(state.get("project_root")) if state.get("project_root") else None
        proj_name = state.get("project_name") or existing_name or folder_name or state.get("epic", {}).get("name", "Épico")
        self.project_repo._update_index_entry(target_pid, proj_name, state.get("project_root"), state)
        if target_pid == self.get_current_project_id():
            self._sync_legacy_file(state)

    def _save_workflow(self, state: Dict[str, Any], filepath: Optional[str] = None):
        self._atomic_write_json(filepath or self.legacy_file, state)

    def _sync_legacy_file(self, state: Dict[str, Any]):
        try:
            self._save_workflow(state, self.legacy_file)
        except Exception:
            pass

    def sync_from_legacy_if_modified(self) -> Optional[str]:
        if not os.path.exists(self.legacy_file):
            return None
        try:
            with self.lock:
                leg_mtime = os.path.getmtime(self.legacy_file)
                with open(self.legacy_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                root = data.get("project_root")
                pid = canonical_project_id(root) if root else self.get_current_project_id()
                pfile = self._get_project_file(pid)
                target_mtime = os.path.getmtime(pfile) if os.path.exists(pfile) else 0
                if leg_mtime > target_mtime:
                    self._atomic_write_json(pfile, data)
                    self.project_repo._update_index_entry(pid, data.get("epic", {}).get("name", os.path.basename(root) if root else "Projeto"), root, data)
                    return pid
        except Exception as e:
            print(f"[StateFacade] Falha ao sincronizar legado: {e}", file=sys.stderr)
        return None

    def reset_state(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            old = self.get_state(target_pid)
            pmeta = self.project_repo._read_index().get("projects", {}).get(target_pid, {})
            root = old.get("project_root") or pmeta.get("project_root")
            name = old.get("epic", {}).get("name") or pmeta.get("name") or "Projeto Resetado"
            state = default_initial_state(project_name=name, project_root=root)
            if root:
                state["project_root"] = root
            for k in ("local_worker", "governance_settings", "settings", "project_settings_overrides"):
                if old.get(k):
                    state[k] = old[k]
            self._save_state(state, target_pid)
        self._notify("STATE_RESET", state, target_pid)
        self._notify("STATE_FULL", state, target_pid)
        return state

    def reset_project(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.reset_state(project_id=project_id)

    def get_metrics(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            nodes, logs = state.get("nodes", []), state.get("gauntlet_log", [])
            tot, app = len(nodes), len([n for n in nodes if n.get("kanban_status") == "APPROVED"])
            attempts = sum(n.get("attempt", 1) for n in nodes)
            fp = len([n for n in nodes if n.get("kanban_status") == "APPROVED" and n.get("attempt", 1) == 1])
            rate = round((fp / app * 100), 1) if app > 0 else 0.0
            tokens = (attempts * 3500) + (len(logs) * 1800) + 12000
            return {
                "project_id": target_pid, "total_slices": tot, "approved_slices": app,
                "total_attempts": attempts, "first_pass_rate": f"{rate}%",
                "estimated_tokens_saved": f"{tokens:,}".replace(",", "."),
                "gauntlet_verdicts_count": len(logs),
                "active_pairs_count": len([p for p in state.get("pairs_3x3", []) if p.get("builder_status") != "IDLE" or p.get("critic_status") != "IDLE"]),
                "last_update": time.strftime("%H:%M:%S")
            }

    def freeze_checkpoint(self, project_id: Optional[str] = None) -> str:
        target_pid = project_id or self.get_current_project_id()
        return self.project_repo.freeze_checkpoint(self.get_state(target_pid), target_pid)

    def read_checkpoint(self, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self.project_repo.read_checkpoint(project_id or self.get_current_project_id())

    @property
    def file_path(self) -> str: return self._get_project_file(self.get_current_project_id())

    # Delegações para ProjectRepository
    def get_current_project_id(self) -> str: return self.project_repo.get_current_project_id()
    def switch_current_project(self, project_id: str) -> str:
        target_pid = self.project_repo.switch_current_project(project_id)
        state = self.get_state(target_pid)
        self._save_state(state, target_pid)
        self._sync_legacy_file(state)
        self._notify("PROJECT_SWITCHED", {"project_id": target_pid}, target_pid)
        self._notify("STATE_FULL", state, target_pid)
        return target_pid
    def list_projects(self) -> List[Dict[str, Any]]: return self.project_repo.list_projects()
    def resolve_project_id(self, project_id: Optional[str] = None, project_root: Optional[str] = None) -> str: return self.project_repo.resolve_project_id(project_id, project_root)
    def set_project_root(self, root_path: str, project_id: Optional[str] = None) -> str:
        target_pid = self.resolve_project_id(project_id, root_path)
        with self.lock:
            state = self.get_state(target_pid)
            state["project_root"] = os.path.abspath(root_path)
            self._save_state(state, target_pid)
        self._notify("PROJECT_ROOT_UPDATED", {"project_root": state["project_root"]}, target_pid)
        self._notify("STATE_FULL", state, target_pid)
        return state["project_root"]
    def get_project_root(self, project_id: Optional[str] = None) -> Optional[str]: return self.get_state(self.resolve_project_id(project_id)).get("project_root")
    def delete_project(self, project_id: str) -> bool:
        res = self.project_repo.delete_project(project_id)
        self._notify("PROJECTS_UPDATED", self.list_projects())
        return res
    def scan_local_projects(self, base_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        res = self.project_repo.scan_local_projects(base_dir)
        self._notify("PROJECTS_UPDATED", self.list_projects())
        return res
    def import_project(self, project_path: str, name: Optional[str] = None, switch: bool = True) -> Dict[str, Any]:
        res = self.project_repo.import_project(project_path, name=name, switch=switch)
        self._notify("PROJECTS_UPDATED", self.list_projects())
        if switch and res.get("current_project_id"):
            self._notify("PROJECT_SWITCHED", {"project_id": res.get("current_project_id")})
        return res
    def purge_stale_or_temp_projects(self) -> Dict[str, Any]:
        res = self.project_repo.purge_stale_or_temp_projects()
        self._notify("PROJECTS_UPDATED", self.list_projects())
        return res
    def verify_worktree_commit_proof(self, repo_root: str, slice_id: str, base_branch: Optional[str] = None) -> Dict[str, Any]:
        return self.project_repo.verify_worktree_commit_proof(repo_root, slice_id, base_branch)
    def detect_base_branch(self, repo_root: str) -> str: return self.project_repo.detect_base_branch(repo_root)


    # Delegações para SliceRepository
    def sync_epic(self, epic_name: str, goal: str, vertical_slices: List[Dict[str, Any]], project_root: Optional[str] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.slice_repo.sync_epic(epic_name, goal, vertical_slices, project_root=project_root, project_id=project_id)
    def update_agent_pulse(self, pair_id: int, builder_status: str, critic_status: str, slice_id: Optional[str] = None, attempt: Optional[int] = None, details_md: Optional[str] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.slice_repo.update_agent_pulse(pair_id, builder_status, critic_status, slice_id=slice_id, attempt=attempt, details_md=details_md, project_id=project_id)
    def set_slice_tdd_stage(self, slice_id: str, stage: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.slice_repo.set_slice_tdd_stage(slice_id, stage, project_id=project_id)
    def log_critique_verdict(self, slice_id: str, attempt: int, verdict: str, reason_md: str, review_metrics: Optional[Dict[str, int]] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.slice_repo.log_critique_verdict(slice_id, attempt, verdict, reason_md, review_metrics=review_metrics, project_id=project_id)
    def add_user_steering(self, text: str, project_id: Optional[str] = None, slice_id: Optional[str] = None) -> Dict[str, Any]:
        return self.slice_repo.add_user_steering(text, project_id=project_id, slice_id=slice_id)
    def fetch_unconsumed_steering(self, project_id: Optional[str] = None, slice_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.slice_repo.fetch_unconsumed_steering(project_id=project_id, slice_id=slice_id)
    def post_orchestrator_message(self, text: str, project_id: Optional[str] = None, slice_id: Optional[str] = None, sender: str = "ORCHESTRATOR") -> Dict[str, Any]:
        return self.slice_repo.post_orchestrator_message(text, project_id=project_id, slice_id=slice_id, sender=sender)
    def get_slice_steering_messages(self, project_id: Optional[str] = None, slice_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.slice_repo.get_slice_steering_messages(project_id=project_id, slice_id=slice_id)
    def get_slice_spec(self, slice_id: str, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self.slice_repo.get_slice_spec(slice_id, project_id=project_id)
    def prune_session_context(self, retain_last_messages: int = 3, retain_last_verdicts: int = 6, project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.slice_repo.prune_session_context(retain_last_messages=retain_last_messages, retain_last_verdicts=retain_last_verdicts, project_id=project_id)
    def register_fleet_anomaly(self, slice_id: Optional[str], anomaly_type: str, details: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.slice_repo.register_fleet_anomaly(slice_id, anomaly_type, details, project_id=project_id)
    def check_fleet_liveness(self, subagents_status: Optional[List[Dict[str, Any]]] = None, repo_root: Optional[str] = None, slice_id: Optional[str] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.slice_repo.check_fleet_liveness(subagents_status=subagents_status, repo_root=repo_root, slice_id=slice_id, project_id=project_id)
    def resume_orchestration(self, project_id: Optional[str] = None, project_root: Optional[str] = None) -> Dict[str, Any]:
        return self.slice_repo.resume_orchestration(project_id=project_id, project_root=project_root)

    # Delegações para SettingsRepository
    def approve_gate(self, gate_name: str, approved_by: str = "user", project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.settings_repo.approve_gate(gate_name, approved_by=approved_by, project_id=project_id)
    def get_gate_status(self, gate_name: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.settings_repo.get_gate_status(gate_name, project_id=project_id)
    def get_governance_settings(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.settings_repo.get_governance_settings(project_id=project_id)
    def update_governance_settings(self, updates: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.settings_repo.update_governance_settings(updates, project_id=project_id)
    def set_last_handoff(self, handoff_meta: Dict[str, Any], project_id: Optional[str] = None):
        self.settings_repo.set_last_handoff(handoff_meta, project_id=project_id)
    def get_last_handoff(self, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self.settings_repo.get_last_handoff(project_id=project_id)
    def get_settings(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.settings_repo.get_settings(project_id=project_id)
    def update_settings(self, updates: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.settings_repo.update_settings(updates, project_id=project_id)
    def get_general_defaults(self) -> Dict[str, Any]: return self.settings_repo.get_general_defaults()
    def get_project_settings(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.settings_repo.get_project_settings(project_id=project_id)
    def set_project_settings(self, project_id: Optional[str], overrides: Dict[str, Any]) -> Dict[str, Any]:
        return self.settings_repo.set_project_settings(project_id, overrides)
    def clear_project_settings_overrides(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.settings_repo.clear_project_settings_overrides(project_id=project_id)
    def get_local_worker_config(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.settings_repo.get_local_worker_config(project_id=project_id)
    def set_local_worker_config(self, updates: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.settings_repo.set_local_worker_config(updates, project_id=project_id)
    def update_local_worker_config(self, updates: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.settings_repo.update_local_worker_config(updates, project_id=project_id)
    def get_local_worker_attempts(self, slice_id: str, project_id: Optional[str] = None) -> int:
        return self.settings_repo.get_local_worker_attempts(slice_id, project_id=project_id)
    def increment_local_worker_attempts(self, slice_id: str, project_id: Optional[str] = None) -> int:
        return self.settings_repo.increment_local_worker_attempts(slice_id, project_id=project_id)
    def reset_local_worker_attempts(self, slice_id: str, project_id: Optional[str] = None) -> None:
        self.settings_repo.reset_local_worker_attempts(slice_id, project_id=project_id)
    def get_circuit_breaker_count(self, slice_id: str, project_id: Optional[str] = None) -> int:
        return self.settings_repo.get_circuit_breaker_count(slice_id, project_id=project_id)
    def increment_circuit_breaker(self, slice_id: str, project_id: Optional[str] = None) -> int:
        return self.settings_repo.increment_circuit_breaker(slice_id, project_id=project_id)
    def reset_circuit_breaker(self, slice_id: str, project_id: Optional[str] = None) -> None:
        self.settings_repo.reset_circuit_breaker(slice_id, project_id=project_id)

StateStoreFacade = StateFacade
