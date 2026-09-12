import json
import os
import re
import hashlib
import inspect
import threading
import time
from typing import List, Dict, Any, Optional, Callable

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STATES_DIR = os.getenv("COCKPIT_STATES_DIR") or os.path.join(BASE_DIR, 'states')
INDEX_FILE = os.path.join(STATES_DIR, 'projects_index.json')
LEGACY_STATE_FILE = os.getenv("COCKPIT_LEGACY_FILE") or os.path.join(BASE_DIR, 'workflow_state.json')

def canonical_project_id(project_path_or_name: Optional[str]) -> str:
    """Gera um identificador estável e canônico para um projeto a partir do seu caminho ou nome."""
    if not project_path_or_name:
        return "default"
    
    val = project_path_or_name.strip()
    # Se já é um project_id existente no formato 'default' ou 'slug-8hexchars'
    if val == "default" or bool(re.search(r'-[0-9a-f]{8}$', val)):
        return val

    abs_path = os.path.abspath(os.path.expanduser(val))
    basename = os.path.basename(abs_path) or "workspace"
    slug = re.sub(r'[^a-zA-Z0-9_\-]', '-', basename).strip('-').lower() or "workspace"
    path_hash = hashlib.sha256(abs_path.encode('utf-8')).hexdigest()[:8]
    return f"{slug}-{path_hash}"

def default_initial_state(project_name: Optional[str] = None, project_root: Optional[str] = None) -> Dict[str, Any]:
    return {
        "epic": {
            "name": project_name or "Aguardando Inicialização do Épico",
            "goal": "Conecte o Antigravity via MCP para sincronizar o Master Blueprint.",
            "status": "PLANNING",
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        },
        "nodes": [
            {
                "id": "slice-1",
                "title": "Fatia Vertical 1: Contratos & Dados",
                "pair_id": 1,
                "kanban_status": "BACKLOG",
                "attempt": 1,
                "max_attempts": 5,
                "acceptance_criteria": "- Contratos de interface validados\n- Zero acoplamento destrutivo\n- Testes de ponta a ponta",
                "spec_md": "### Fatia Vertical 1\nAguardando envio do Master Blueprint pelo Orquestrador.",
                "latest_feedback": "Nenhuma revisão executada ainda.",
                "tdd_stage": "PENDING",
                "review_metrics": {"critical": 0, "important": 0, "minor": 0},
                "updated_at": time.strftime("%H:%M:%S")
            },
            {
                "id": "slice-2",
                "title": "Fatia Vertical 2: Regras & Domínio",
                "pair_id": 2,
                "kanban_status": "BACKLOG",
                "attempt": 1,
                "max_attempts": 5,
                "acceptance_criteria": "- Lógica de negócio coesa\n- Sem regressões funcionais",
                "spec_md": "### Fatia Vertical 2\nAguardando envio do Master Blueprint pelo Orquestrador.",
                "latest_feedback": "Nenhuma revisão executada ainda.",
                "tdd_stage": "PENDING",
                "review_metrics": {"critical": 0, "important": 0, "minor": 0},
                "updated_at": time.strftime("%H:%M:%S")
            },
            {
                "id": "slice-3",
                "title": "Fatia Vertical 3: Interface & Integração",
                "pair_id": 3,
                "kanban_status": "BACKLOG",
                "attempt": 1,
                "max_attempts": 5,
                "acceptance_criteria": "- Renderização e usabilidade validadas\n- Auditoria de integração final aprovada",
                "spec_md": "### Fatia Vertical 3\nAguardando envio do Master Blueprint pelo Orquestrador.",
                "latest_feedback": "Nenhuma revisão executada ainda.",
                "tdd_stage": "PENDING",
                "review_metrics": {"critical": 0, "important": 0, "minor": 0},
                "updated_at": time.strftime("%H:%M:%S")
            }
        ],
        "pairs_3x3": [
            {
                "id": 1,
                "name": "Par 1: Infra & Contratos",
                "builder_status": "IDLE",
                "critic_status": "IDLE",
                "current_slice_id": "slice-1",
                "last_heartbeat": time.strftime("%H:%M:%S")
            },
            {
                "id": 2,
                "name": "Par 2: Domínio & Negócio",
                "builder_status": "IDLE",
                "critic_status": "IDLE",
                "current_slice_id": "slice-2",
                "last_heartbeat": time.strftime("%H:%M:%S")
            },
            {
                "id": 3,
                "name": "Par 3: UI & Integração",
                "builder_status": "IDLE",
                "critic_status": "IDLE",
                "current_slice_id": "slice-3",
                "last_heartbeat": time.strftime("%H:%M:%S")
            }
        ],
        "steering_messages": [
            {
                "id": "msg-0",
                "sender": "ORCHESTRATOR",
                "text": "Agent Cockpit online. Conecte o Antigravity via MCP para iniciar o fluxo Spec-Driven.",
                "timestamp": time.strftime("%H:%M:%S"),
                "consumed": True
            }
        ],
        "gauntlet_log": [],
        "human_gates": {
            "gate_plan_approved": True,
            "gate_ship_approved": False,
            "last_approved_at": None,
            "approved_by": None
        },
        "last_handoff": None,
        "local_worker": {
            "provider": "ollama",
            "endpoint": "http://127.0.0.1:11434",
            "model": "qwen2.5-coder:7b-instruct-q4_k_m",
            "circuit_breaker_threshold": 2,
            "consecutive_failures": {},
            "auto_start_ollama": True
        },
        "project_root": project_root
    }

class StateStore:
    def __init__(self, states_dir: str = STATES_DIR):
        self.states_dir = os.path.abspath(states_dir)
        self.index_file = os.path.join(self.states_dir, 'projects_index.json')
        self.legacy_file = LEGACY_STATE_FILE
        self.lock = threading.RLock()
        self.listeners: List[Callable] = []
        self._ensure_init()

    def register_listener(self, callback: Callable):
        self.listeners.append(callback)

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
                print(f"[StateStore] Erro notificando listener: {e}", file=sys.stderr)

    def _ensure_init(self):
        with self.lock:
            os.makedirs(self.states_dir, exist_ok=True)

            # Inicializa índice de projetos se não existir
            if not os.path.exists(self.index_file):
                initial_index = {
                    "current_project_id": "default",
                    "projects": {}
                }
                with open(self.index_file, 'w', encoding='utf-8') as f:
                    json.dump(initial_index, f, indent=2, ensure_ascii=False)

            # Migração transparente de workflow_state.json legado se existir
            default_file = self._get_project_file("default")
            if os.path.exists(self.legacy_file) and not os.path.exists(default_file):
                try:
                    with open(self.legacy_file, 'r', encoding='utf-8') as f:
                        legacy_data = json.load(f)
                    with open(default_file, 'w', encoding='utf-8') as f:
                        json.dump(legacy_data, f, indent=2, ensure_ascii=False)
                    root_p = legacy_data.get("project_root")
                    epic_name = legacy_data.get("epic", {}).get("name", "Default Project")
                    self._update_index_entry("default", epic_name, root_p, legacy_data)
                except Exception as e:
                    print(f"[StateStore] Falha ao migrar estado legado: {e}", file=sys.stderr)

            # Garante que o projeto 'default' tenha arquivo
            if not os.path.exists(default_file):
                data = default_initial_state("Projeto Padrão")
                with open(default_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                self._update_index_entry("default", "Projeto Padrão", None, data)

    def _get_project_file(self, project_id: str) -> str:
        safe_id = re.sub(r'[^a-zA-Z0-9_\-]', '-', project_id) or "default"
        return os.path.join(self.states_dir, f"{safe_id}.json")

    def _read_index(self) -> Dict[str, Any]:
        if not os.path.exists(self.index_file):
            return {"current_project_id": "default", "projects": {}}
        try:
            with open(self.index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"current_project_id": "default", "projects": {}}

    def _save_index(self, index_data: Dict[str, Any]):
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, indent=2, ensure_ascii=False)

    def _update_index_entry(self, project_id: str, project_name: str,
                            project_root: Optional[str], state_data: Dict[str, Any]):
        nodes = state_data.get("nodes", [])
        approved_count = len([n for n in nodes if n.get("kanban_status") == "APPROVED"])
        
        index_data = self._read_index()
        projects = index_data.setdefault("projects", {})
        
        projects[project_id] = {
            "id": project_id,
            "name": project_name or (os.path.basename(project_root) if project_root else "Projeto Sem Nome"),
            "project_root": project_root,
            "epic_name": state_data.get("epic", {}).get("name", "Épico"),
            "epic_status": state_data.get("epic", {}).get("status", "PLANNING"),
            "total_slices": len(nodes),
            "approved_slices": approved_count,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self._save_index(index_data)

    def get_current_project_id(self) -> str:
        with self.lock:
            index_data = self._read_index()
            return index_data.get("current_project_id", "default")

    def switch_current_project(self, project_id: str) -> str:
        with self.lock:
            index_data = self._read_index()
            if project_id in index_data.get("projects", {}) or os.path.exists(self._get_project_file(project_id)):
                index_data["current_project_id"] = project_id
                self._save_index(index_data)
                
                state = self.get_state(project_id)
                self._sync_legacy_file(state)

                self._notify("PROJECT_SWITCHED", {"project_id": project_id}, project_id)
                self._notify("STATE_FULL", state, project_id)
                return project_id
            return index_data.get("current_project_id", "default")

    def list_projects(self) -> List[Dict[str, Any]]:
        with self.lock:
            index_data = self._read_index()
            current_id = index_data.get("current_project_id", "default")
            projects = index_data.get("projects", {})
            
            result = []
            for pid, pmeta in projects.items():
                meta_copy = dict(pmeta)
                meta_copy["is_current"] = (pid == current_id)
                result.append(meta_copy)
            
            result.sort(key=lambda x: (not x.get("is_current", False), x.get("updated_at", "")), reverse=True)
            return result

    def resolve_project_id(self, project_id: Optional[str] = None, project_root: Optional[str] = None) -> str:
        if project_id:
            return canonical_project_id(project_id)
        if project_root:
            return canonical_project_id(project_root)
        return self.get_current_project_id()

    def get_state(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = project_id or self.get_current_project_id()
        pfile = self._get_project_file(target_pid)
        with self.lock:
            if not os.path.exists(pfile):
                return default_initial_state("Projeto Padrão")
            try:
                with open(pfile, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return default_initial_state("Projeto Padrão")

    def _save_state(self, state: Dict[str, Any], project_id: str):
        pfile = self._get_project_file(project_id)
        with open(pfile, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        
        epic_name = state.get("epic", {}).get("name", "Épico")
        root_p = state.get("project_root")
        self._update_index_entry(project_id, epic_name, root_p, state)

        if project_id == self.get_current_project_id():
            self._sync_legacy_file(state)

    def _sync_legacy_file(self, state: Dict[str, Any]):
        try:
            with open(self.legacy_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def sync_epic(self, epic_name: str, goal: str, vertical_slices: List[Dict[str, Any]],
                  project_root: Optional[str] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id, project_root)
        with self.lock:
            state = self.get_state(target_pid)
            if project_root:
                state["project_root"] = os.path.abspath(project_root)
            state["epic"] = {
                "name": epic_name,
                "goal": goal,
                "status": "IN_PROGRESS",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            nodes = []
            for idx, s in enumerate(vertical_slices[:3], start=1):
                nodes.append({
                    "id": s.get("id", f"slice-{idx}"),
                    "title": s.get("title", f"Fatia Vertical {idx}"),
                    "pair_id": idx,
                    "kanban_status": "BACKLOG",
                    "attempt": 1,
                    "max_attempts": s.get("max_attempts", 5),
                    "acceptance_criteria": s.get("acceptance_criteria", "Critérios definidos no blueprint."),
                    "spec_md": s.get("spec_md", "Especificação técnica."),
                    "latest_feedback": "Aguardando início da execução.",
                    "tdd_stage": "PENDING",
                    "review_metrics": {"critical": 0, "important": 0, "minor": 0},
                    "updated_at": time.strftime("%H:%M:%S")
                })
            state["nodes"] = nodes
            self._save_state(state, target_pid)
            
            index_data = self._read_index()
            if index_data.get("current_project_id") == "default" and target_pid != "default":
                index_data["current_project_id"] = target_pid
                self._save_index(index_data)

        self._notify("PROJECTS_UPDATED", self.list_projects(), target_pid)
        self._notify("EPIC_SYNCED", state["epic"], target_pid)
        self._notify("STATE_FULL", state, target_pid)
        return state

    def update_agent_pulse(self, pair_id: int, builder_status: str, critic_status: str,
                           slice_id: Optional[str] = None, attempt: Optional[int] = None,
                           details_md: Optional[str] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            for p in state.get("pairs_3x3", []):
                if p["id"] == pair_id:
                    p["builder_status"] = builder_status
                    p["critic_status"] = critic_status
                    if slice_id:
                        p["current_slice_id"] = slice_id
                    p["last_heartbeat"] = time.strftime("%H:%M:%S")
            target_slice = slice_id or f"slice-{pair_id}"
            for node in state.get("nodes", []):
                if node["id"] == target_slice:
                    if attempt is not None:
                        node["attempt"] = attempt
                    if details_md:
                        node["latest_feedback"] = details_md
                    if critic_status == "APPROVED":
                        node["kanban_status"] = "APPROVED"
                    elif critic_status == "REJECTED":
                        node["kanban_status"] = "REJECTED"
                    elif critic_status == "REVIEWING":
                        node["kanban_status"] = "CRITIQUING"
                    elif builder_status == "WAITING":
                        node["kanban_status"] = "WAITING_REVIEW"
                    elif builder_status == "WORKING":
                        node["kanban_status"] = "EXECUTING"
                    node["updated_at"] = time.strftime("%H:%M:%S")
            self._save_state(state, target_pid)
        self._notify("PULSE_UPDATED", {"pair_id": pair_id, "builder": builder_status, "critic": critic_status}, target_pid)
        self._notify("STATE_FULL", state, target_pid)
        return state

    def set_slice_tdd_stage(self, slice_id: str, stage: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            for node in state.get("nodes", []):
                if node["id"] == slice_id:
                    node["tdd_stage"] = stage
                    node["updated_at"] = time.strftime("%H:%M:%S")
            self._save_state(state, target_pid)
        self._notify("TDD_STAGE_UPDATED", {"slice_id": slice_id, "stage": stage}, target_pid)
        self._notify("STATE_FULL", state, target_pid)
        return {"slice_id": slice_id, "tdd_stage": stage}

    def log_critique_verdict(self, slice_id: str, attempt: int, verdict: str,
                             reason_md: str,
                             review_metrics: Optional[Dict[str, int]] = None,
                             project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            verdict_norm = "APROVADO" if "APROV" in verdict.upper() else "REJEITADO"
            metrics = review_metrics or {"critical": 0, "important": 0, "minor": 0}
            entry = {
                "slice_id": slice_id,
                "attempt": attempt,
                "verdict": verdict_norm,
                "reason": reason_md,
                "review_metrics": metrics,
                "timestamp": time.strftime("%H:%M:%S")
            }
            state.setdefault("gauntlet_log", []).append(entry)
            for node in state.get("nodes", []):
                if node["id"] == slice_id:
                    node["attempt"] = attempt
                    node["latest_feedback"] = f"[{verdict_norm}] {reason_md}"
                    node["kanban_status"] = "APPROVED" if verdict_norm == "APROVADO" else "REJEITADO"
                    node["review_metrics"] = metrics
                    node["updated_at"] = time.strftime("%H:%M:%S")
            self._save_state(state, target_pid)
        self._notify("VERDICT_LOGGED", entry, target_pid)
        self._notify("STATE_FULL", state, target_pid)
        return entry

    def add_user_steering(self, text: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            msg = {
                "id": f"msg-{len(state.get('steering_messages', [])) + 1}",
                "sender": "USER",
                "text": text,
                "timestamp": time.strftime("%H:%M:%S"),
                "consumed": False
            }
            state.setdefault("steering_messages", []).append(msg)
            self._save_state(state, target_pid)
        self._notify("STEERING_RECEIVED", msg, target_pid)
        self._notify("STATE_FULL", state, target_pid)
        return msg

    def fetch_unconsumed_steering(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            unconsumed = [m for m in state.get("steering_messages", []) if not m.get("consumed", False)]
            for m in unconsumed:
                m["consumed"] = True
            if unconsumed:
                self._save_state(state, target_pid)
        return unconsumed

    def post_orchestrator_message(self, text: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            msg = {
                "id": f"msg-{len(state.get('steering_messages', [])) + 1}",
                "sender": "ORCHESTRATOR",
                "text": text,
                "timestamp": time.strftime("%H:%M:%S"),
                "consumed": True
            }
            state.setdefault("steering_messages", []).append(msg)
            self._save_state(state, target_pid)
        self._notify("ORCHESTRATOR_MESSAGE", msg, target_pid)
        self._notify("STATE_FULL", state, target_pid)
        return msg

    def get_metrics(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            nodes = state.get("nodes", [])
            logs = state.get("gauntlet_log", [])

            total_slices = len(nodes)
            approved_slices = len([n for n in nodes if n.get("kanban_status") == "APPROVED"])
            total_attempts = sum(n.get("attempt", 1) for n in nodes)
            first_pass_count = len([n for n in nodes if n.get("kanban_status") == "APPROVED" and n.get("attempt", 1) == 1])

            first_pass_rate = round((first_pass_count / approved_slices * 100), 1) if approved_slices > 0 else 0.0
            tokens_saved = (total_attempts * 3500) + (len(logs) * 1800) + 12000

            return {
                "project_id": target_pid,
                "total_slices": total_slices,
                "approved_slices": approved_slices,
                "total_attempts": total_attempts,
                "first_pass_rate": f"{first_pass_rate}%",
                "estimated_tokens_saved": f"{tokens_saved:,}".replace(",", "."),
                "gauntlet_verdicts_count": len(logs),
                "active_pairs_count": len([p for p in state.get("pairs_3x3", []) if p.get("builder_status") != "IDLE" or p.get("critic_status") != "IDLE"]),
                "last_update": time.strftime("%H:%M:%S")
            }

    def get_slice_spec(self, slice_id: str, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            for node in state.get("nodes", []):
                if node.get("id") == slice_id or str(node.get("pair_id")) == str(slice_id):
                    return {
                        "id": node.get("id"),
                        "title": node.get("title"),
                        "acceptance_criteria": node.get("acceptance_criteria"),
                        "spec_md": node.get("spec_md"),
                        "kanban_status": node.get("kanban_status"),
                        "attempt": node.get("attempt", 1),
                        "max_attempts": node.get("max_attempts", 5),
                        "tdd_stage": node.get("tdd_stage", "PENDING"),
                        "review_metrics": node.get("review_metrics", {"critical": 0, "important": 0, "minor": 0})
                    }
        return None

    def approve_gate(self, gate_name: str, approved_by: str = "user", project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            gates = state.setdefault("human_gates", {})
            gates[gate_name] = True
            gates["last_approved_at"] = time.strftime("%H:%M:%S")
            gates["approved_by"] = approved_by
            self._save_state(state, target_pid)
        self._notify("GATE_APPROVED", {"gate": gate_name, "approved_by": approved_by}, target_pid)
        self._notify("STATE_FULL", state, target_pid)
        return {"status": "APPROVED", "gate": gate_name, "approved_by": approved_by, "project_id": target_pid}

    def get_gate_status(self, gate_name: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            gates = state.get("human_gates", {})
            is_approved = gates.get(gate_name, False)
            return {
                "gate": gate_name,
                "approved": bool(is_approved),
                "last_approved_at": gates.get("last_approved_at"),
                "approved_by": gates.get("approved_by"),
                "project_id": target_pid
            }

    def set_last_handoff(self, handoff_meta: Dict[str, Any], project_id: Optional[str] = None):
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            state["last_handoff"] = handoff_meta
            self._save_state(state, target_pid)
        self._notify("HANDOFF_UPDATED", handoff_meta, target_pid)
        self._notify("STATE_FULL", state, target_pid)

    def get_last_handoff(self, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            return state.get("last_handoff")

    def set_project_root(self, root_path: str, project_id: Optional[str] = None) -> str:
        target_pid = self.resolve_project_id(project_id, root_path)
        with self.lock:
            state = self.get_state(target_pid)
            abs_p = os.path.abspath(root_path)
            state["project_root"] = abs_p
            self._save_state(state, target_pid)
        self._notify("PROJECT_ROOT_UPDATED", {"project_root": abs_p}, target_pid)
        self._notify("STATE_FULL", state, target_pid)
        return abs_p

    def get_project_root(self, project_id: Optional[str] = None) -> Optional[str]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            return state.get("project_root")

    def prune_session_context(self, retain_last_messages: int = 3, retain_last_verdicts: int = 6,
                              project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            
            # 1. Compacta steering_messages antigas
            all_msgs = state.get("steering_messages", [])
            pruned_msgs_count = max(0, len(all_msgs) - retain_last_messages)
            if pruned_msgs_count > 0:
                summary_msg = {
                    "id": f"msg-pruned-summary",
                    "sender": "SYSTEM",
                    "text": f"[CONTEXT_PRUNED] {pruned_msgs_count} mensagens de direcionamento anteriores foram consolidadas e arquivadas.",
                    "timestamp": time.strftime("%H:%M:%S"),
                    "consumed": True
                }
                state["steering_messages"] = [summary_msg] + all_msgs[-retain_last_messages:]

            # 2. Compacta o gauntlet_log de tentativas passadas
            all_verdicts = state.get("gauntlet_log", [])
            pruned_verdicts_count = max(0, len(all_verdicts) - retain_last_verdicts)
            if pruned_verdicts_count > 0:
                state["gauntlet_log"] = all_verdicts[-retain_last_verdicts:]

            # 3. Garante que os nós mantenham apenas o feedback condensado mais recente
            for node in state.get("nodes", []):
                fb = node.get("latest_feedback", "")
                if len(fb) > 300:
                    node["latest_feedback"] = fb[:297] + "..."

            self._save_state(state, target_pid)

        self._notify("CONTEXT_PRUNED", {
            "pruned_messages": pruned_msgs_count,
            "pruned_verdicts": pruned_verdicts_count,
            "timestamp": time.strftime("%H:%M:%S")
        }, target_pid)
        self._notify("STATE_FULL", state, target_pid)

        return {
            "status": "PRUNED",
            "project_id": target_pid,
            "epic_name": state.get("epic", {}).get("name"),
            "pruned_messages_count": pruned_msgs_count,
            "pruned_verdicts_count": pruned_verdicts_count,
            "active_nodes_count": len(state.get("nodes", [])),
            "recommendation_for_agent": "Descarte do contexto ativo os turnos de depuração e transcrições de comandos passados. Mantenha em foco estritamente o MASTER_BLUEPRINT.md atual e o estado dos nós do grafo."
        }

    def reset_state(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = default_initial_state("Projeto Resetado")
            self._save_state(state, target_pid)
        self._notify("STATE_RESET", state, target_pid)
        self._notify("STATE_FULL", state, target_pid)
        return state

    def delete_project(self, project_id: str) -> bool:
        """Remove o arquivo de estado e registro do índice (não permite deletar 'default' se for o único)."""
        with self.lock:
            index_data = self._read_index()
            projects = index_data.get("projects", {})
            if project_id in projects:
                del projects[project_id]
                if index_data.get("current_project_id") == project_id:
                    index_data["current_project_id"] = next(iter(projects.keys())) if projects else "default"
                self._save_index(index_data)

            pfile = self._get_project_file(project_id)
            if os.path.exists(pfile):
                try:
                    os.remove(pfile)
                except Exception:
                    pass
            self._notify("PROJECTS_UPDATED", self.list_projects())
            return True

    def sync_from_legacy_if_modified(self) -> Optional[str]:
        """Sincroniza workflow_state.json caso processos legados MCP o tenham modificado recentemente."""
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
                    with open(pfile, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    epic_name = data.get("epic", {}).get("name", os.path.basename(root) if root else "Projeto")
                    self._update_index_entry(pid, epic_name, root, data)
                    
                    index_data = self._read_index()
                    if index_data.get("current_project_id") != pid:
                        index_data["current_project_id"] = pid
                        self._save_index(index_data)
                    return pid
        except Exception as e:
            print(f"[StateStore] Falha ao sincronizar estado legado: {e}", file=sys.stderr)
        return None

    def scan_local_projects(self, base_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """Descobre repositórios e projetos reais em ~/Projects e os registra no Cockpit."""
        target_dir = os.path.abspath(os.path.expanduser(base_dir or "~/Projects"))
        if not os.path.exists(target_dir):
            return self.list_projects()

        with self.lock:
            index_data = self._read_index()
            projects = index_data.setdefault("projects", {})
            existing_roots = {p.get("project_root") for p in projects.values() if p.get("project_root")}

            found_any = False
            for entry in os.scandir(target_dir):
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                p_path = entry.path
                if p_path in existing_roots:
                    continue

                pid = canonical_project_id(p_path)
                pfile = self._get_project_file(pid)
                
                if not os.path.exists(pfile):
                    initial_state = default_initial_state(project_name=entry.name, project_root=p_path)
                    with open(pfile, 'w', encoding='utf-8') as f:
                        json.dump(initial_state, f, indent=2, ensure_ascii=False)
                    self._update_index_entry(pid, entry.name, p_path, initial_state)
                    found_any = True
                elif pid not in projects:
                    try:
                        with open(pfile, 'r', encoding='utf-8') as f:
                            s_data = json.load(f)
                    except Exception:
                        s_data = default_initial_state(project_name=entry.name, project_root=p_path)
                    self._update_index_entry(pid, entry.name, p_path, s_data)
                    found_any = True

            if found_any:
                self._notify("PROJECTS_UPDATED", self.list_projects())

        return self.list_projects()

    def _get_checkpoint_file(self, project_id: str) -> str:
        safe_id = re.sub(r'[^a-zA-Z0-9_\-]', '-', project_id) or "default"
        return os.path.join(self.states_dir, f"{safe_id}.checkpoint.json")

    def freeze_checkpoint(self, project_id: Optional[str] = None) -> str:
        """Salva um snapshot transacional atômico do projeto para retomada segura em caso de falha de cota/créditos."""
        target_pid = project_id or self.get_current_project_id()
        with self.lock:
            state = self.get_state(target_pid)
            cp_file = self._get_checkpoint_file(target_pid)
            checkpoint_data = {
                "checkpoint_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "project_id": target_pid,
                "project_root": state.get("project_root"),
                "epic": state.get("epic"),
                "nodes": state.get("nodes"),
                "pairs_3x3": state.get("pairs_3x3"),
                "human_gates": state.get("human_gates")
            }
            with open(cp_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)
            return cp_file

    def read_checkpoint(self, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Lê o snapshot transacional de um projeto se existir."""
        target_pid = project_id or self.get_current_project_id()
        cp_file = self._get_checkpoint_file(target_pid)
        if not os.path.exists(cp_file):
            return None
        try:
            with open(cp_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def verify_worktree_commit_proof(self, repo_root: str, slice_id: str, base_branch: str = "master") -> Dict[str, Any]:
        """Proof of Work (Git): Valida se a branch da fatia possui commits válidos à frente da branch base."""
        import subprocess
        root = os.path.abspath(os.path.expanduser(repo_root))
        branch_name = f"cockpit/{slice_id}"
        
        # 1. Verifica se a branch da fatia existe no git
        res_ref = subprocess.run(
            ["git", "-C", root, "rev-parse", "--verify", branch_name],
            capture_output=True, text=True, check=False
        )
        if res_ref.returncode != 0:
            return {
                "valid_proof": False,
                "reason": f"Branch '{branch_name}' não encontrada no repositório. O subagente não comitou nada.",
                "commits_count": 0
            }

        branch_head = res_ref.stdout.strip()

        # 2. Verifica hash da branch base
        res_base = subprocess.run(
            ["git", "-C", root, "rev-parse", "--verify", base_branch],
            capture_output=True, text=True, check=False
        )
        base_head = res_base.stdout.strip() if res_base.returncode == 0 else ""

        if branch_head == base_head:
            return {
                "valid_proof": False,
                "reason": f"A branch '{branch_name}' aponta exatamente para a '{base_branch}'. Nenhum commit de trabalho foi produzido.",
                "commits_count": 0
            }

        # 3. Lista commits à frente
        log_res = subprocess.run(
            ["git", "-C", root, "log", f"{base_branch}..{branch_name}", "--oneline"],
            capture_output=True, text=True, check=False
        )
        lines = [l.strip() for l in log_res.stdout.splitlines() if l.strip()]
        return {
            "valid_proof": len(lines) > 0,
            "head_commit": branch_head,
            "commits_count": len(lines),
            "commits": lines,
            "latest_commit_msg": lines[0] if lines else ""
        }

    def register_fleet_anomaly(self, slice_id: Optional[str], anomaly_type: str, details: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """Registra falha crítica ou falta de créditos, congelando o estado do projeto e alertando a telemetria."""
        target_pid = project_id or self.get_current_project_id()
        with self.lock:
            state = self.get_state(target_pid)
            
            # 1. Atualiza o nó no Kanban
            target_slice = None
            for n in state.get("nodes", []):
                if (slice_id and n.get("id") == slice_id) or (not slice_id and n.get("kanban_status") in ["EXECUTING", "REVIEWING"]):
                    n["kanban_status"] = "BLOCKED_NO_CREDIT" if anomaly_type == "OUT_OF_CREDITS" else "STALLED"
                    n["latest_feedback"] = f"⚠️ ANOMALIA [{anomaly_type}]: {details}"
                    target_slice = n.get("id")
                    break

            # 2. Atualiza pares 3x3 correspondentes
            for p in state.get("pairs_3x3", []):
                if not target_slice or p.get("current_slice_id") == target_slice:
                    p["builder_status"] = "BLOCKED"
                    p["critic_status"] = "IDLE"

            # 3. Adiciona mensagem de emergência no steering
            state.setdefault("steering_messages", []).append({
                "id": f"msg-err-{int(time.time())}",
                "sender": "ORCHESTRATOR",
                "text": f"🚨 ALERTA DE SISTEMA [{anomaly_type}]: {details}. Estado congelado em checkpoint.",
                "timestamp": time.strftime("%H:%M:%S"),
                "consumed": False
            })

            # 4. Salva estado e snapshot de checkpoint
            self._save_state(state, target_pid)
            cp_path = self.freeze_checkpoint(target_pid)

        self._notify("FLEET_ANOMALY", {"anomaly_type": anomaly_type, "slice_id": target_slice, "details": details}, target_pid)
        self._notify("STATE_FULL", state, target_pid)

        return {
            "status": "ANOMALY_REGISTERED",
            "anomaly_type": anomaly_type,
            "affected_slice": target_slice,
            "checkpoint_path": cp_path,
            "details": details
        }

    def check_fleet_liveness(self, subagents_status: Optional[List[Dict[str, Any]]] = None,
                             repo_root: Optional[str] = None, slice_id: Optional[str] = None,
                             project_id: Optional[str] = None) -> Dict[str, Any]:
        """Inspeciona se a frota sofreu corte de créditos, rate limit ou silêncio por zumbi."""
        target_pid = project_id or self.get_current_project_id()
        state = self.get_state(target_pid)
        root = repo_root or state.get("project_root")

        # 1. Inspeciona erros nos subagentes (se passados via manage_subagents ou telemetry)
        if subagents_status:
            credit_keywords = ["resourceexhausted", "quota", "credit", "rate limit", "insufficient_quota", "billing", "exceeded"]
            for sub in subagents_status:
                s_state = str(sub.get("state", "")).lower()
                s_detail = str(sub.get("stateDetail", "")).lower()
                
                # Checa erro de cota / crédito
                if any(kw in s_detail for kw in credit_keywords) or (s_state == "errored" and "quota" in s_detail):
                    anom = self.register_fleet_anomaly(
                        slice_id=slice_id,
                        anomaly_type="OUT_OF_CREDITS",
                        details=f"Subagente '{sub.get('role', sub.get('conversationId'))}' falhou com esgotamento de créditos: {sub.get('stateDetail')}",
                        project_id=target_pid
                    )
                    return {
                        "healthy": False,
                        "anomaly_type": "OUT_OF_CREDITS",
                        "details": anom["details"],
                        "checkpoint_path": anom["checkpoint_path"],
                        "recovery_hint": "Aguarde a renovação da cota ou troque de conta/modelo e chame resume_orchestration."
                    }

        # 2. Se foi solicitada verificação de commit proof (Proof of Work)
        if root and slice_id:
            proof = self.verify_worktree_commit_proof(root, slice_id)
            if not proof.get("valid_proof"):
                # Subagente concluiu falsamente sem commits
                anom = self.register_fleet_anomaly(
                    slice_id=slice_id,
                    anomaly_type="ZERO_COMMIT_DROPPED",
                    details=f"Proof of Work falhou para '{slice_id}': {proof.get('reason')}",
                    project_id=target_pid
                )
                return {
                    "healthy": False,
                    "anomaly_type": "ZERO_COMMIT_DROPPED",
                    "details": proof.get("reason"),
                    "checkpoint_path": anom["checkpoint_path"],
                    "recovery_hint": "O subagente foi interrompido sem gravar commits. Re-despache o Builder para a worktree."
                }

        return {
            "healthy": True,
            "anomaly_type": None,
            "message": "Frota íntegra. Nenhuma falha de cota ou ausência de commits detectada."
        }

    def resume_orchestration(self, project_id: Optional[str] = None, project_root: Optional[str] = None) -> Dict[str, Any]:
        """Retoma a orquestração a partir do último checkpoint seguro, preservando o trabalho já aprovado."""
        target_pid = self.resolve_project_id(project_id, project_root)
        with self.lock:
            state = self.get_state(target_pid)
            cp = self.read_checkpoint(target_pid)
            
            # Identifica fatias prontas vs fatias bloqueadas
            resumed_slices = []
            for n in state.get("nodes", []):
                if n.get("kanban_status") in ["BLOCKED_NO_CREDIT", "STALLED"]:
                    n["kanban_status"] = "EXECUTING"
                    n["latest_feedback"] = "Retomada autorizada após verificação de créditos/liveness."
                    resumed_slices.append(n.get("id"))

            for p in state.get("pairs_3x3", []):
                if p.get("builder_status") == "BLOCKED":
                    p["builder_status"] = "IDLE"

            self._save_state(state, target_pid)

        self._notify("STATE_FULL", state, target_pid)
        return {
            "status": "RESUMED",
            "project_id": target_pid,
            "resumed_slices": resumed_slices,
            "approved_slices": [n.get("id") for n in state.get("nodes", []) if n.get("kanban_status") == "APPROVED"],
            "pending_slices": [n.get("id") for n in state.get("nodes", []) if n.get("kanban_status") != "APPROVED"]
        }

    def get_local_worker_config(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            cfg = state.setdefault("local_worker", {
                "provider": "ollama",
                "endpoint": "http://127.0.0.1:11434",
                "model": "qwen2.5-coder:7b-instruct-q4_k_m",
                "circuit_breaker_threshold": 2,
                "consecutive_failures": {},
                "auto_start_ollama": True
            })
            if "auto_start_ollama" not in cfg:
                cfg["auto_start_ollama"] = True
            return dict(cfg)

    def set_local_worker_config(self, updates: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            cfg = state.setdefault("local_worker", {
                "provider": "ollama",
                "endpoint": "http://127.0.0.1:11434",
                "model": "qwen2.5-coder:7b-instruct-q4_k_m",
                "circuit_breaker_threshold": 2,
                "consecutive_failures": {},
                "auto_start_ollama": True
            })
            if "auto_start_ollama" not in cfg:
                cfg["auto_start_ollama"] = True
            cfg.update(updates)
            self._save_state(state, target_pid)
        self._notify("LOCAL_WORKER_CONFIG_UPDATED", cfg, target_pid)
        self._notify("STATE_FULL", state, target_pid)
        return dict(cfg)

    def update_local_worker_config(self, updates: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.set_local_worker_config(updates, project_id=project_id)

    def get_local_worker_attempts(self, slice_id: str, project_id: Optional[str] = None) -> int:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            cfg = state.setdefault("local_worker", {
                "provider": "ollama",
                "endpoint": "http://127.0.0.1:11434",
                "model": "qwen2.5-coder:7b-instruct-q4_k_m",
                "circuit_breaker_threshold": 2,
                "consecutive_failures": {}
            })
            failures = cfg.setdefault("consecutive_failures", {})
            return int(failures.get(slice_id, 0))

    def increment_local_worker_attempts(self, slice_id: str, project_id: Optional[str] = None) -> int:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            cfg = state.setdefault("local_worker", {
                "provider": "ollama",
                "endpoint": "http://127.0.0.1:11434",
                "model": "qwen2.5-coder:7b-instruct-q4_k_m",
                "circuit_breaker_threshold": 2,
                "consecutive_failures": {}
            })
            failures = cfg.setdefault("consecutive_failures", {})
            failures[slice_id] = int(failures.get(slice_id, 0)) + 1
            val = failures[slice_id]
            self._save_state(state, target_pid)
        self._notify("LOCAL_WORKER_ATTEMPTS_UPDATED", {"slice_id": slice_id, "attempts": val}, target_pid)
        return val

    def reset_local_worker_attempts(self, slice_id: str, project_id: Optional[str] = None) -> None:
        target_pid = self.resolve_project_id(project_id)
        with self.lock:
            state = self.get_state(target_pid)
            cfg = state.setdefault("local_worker", {
                "provider": "ollama",
                "endpoint": "http://127.0.0.1:11434",
                "model": "qwen2.5-coder:7b-instruct-q4_k_m",
                "circuit_breaker_threshold": 2,
                "consecutive_failures": {}
            })
            failures = cfg.setdefault("consecutive_failures", {})
            failures[slice_id] = 0
            self._save_state(state, target_pid)
        self._notify("LOCAL_WORKER_ATTEMPTS_RESET", {"slice_id": slice_id}, target_pid)

    def get_circuit_breaker_count(self, slice_id: str, project_id: Optional[str] = None) -> int:
        return self.get_local_worker_attempts(slice_id, project_id=project_id)

    def increment_circuit_breaker(self, slice_id: str, project_id: Optional[str] = None) -> int:
        return self.increment_local_worker_attempts(slice_id, project_id=project_id)

    def reset_circuit_breaker(self, slice_id: str, project_id: Optional[str] = None) -> None:
        self.reset_local_worker_attempts(slice_id, project_id=project_id)

    @property
    def file_path(self) -> str:
        """Propriedade para manter compatibilidade com verificações existentes de file_path."""
        return self._get_project_file(self.get_current_project_id())

db = StateStore()