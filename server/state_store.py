import json
import os
import threading
import time
from typing import List, Dict, Any, Optional, Callable

STATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'workflow_state.json')

def default_initial_state() -> Dict[str, Any]:
    return {
        "epic": {
            "name": "Aguardando Inicialização do Épico",
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
        "gauntlet_log": []
    }

class StateStore:
    def __init__(self, file_path: str = STATE_FILE):
        self.file_path = os.path.abspath(file_path)
        self.lock = threading.RLock()
        self.listeners: List[Callable[[str, Any], None]] = []
        self._ensure_init()

    def register_listener(self, callback: Callable[[str, Any], None]):
        self.listeners.append(callback)

    def _notify(self, event_type: str, payload: Any):
        for listener in self.listeners:
            try:
                listener(event_type, payload)
            except Exception as e:
                print(f"[StateStore] Erro notificando listener: {e}")

    def _ensure_init(self):
        with self.lock:
            if not os.path.exists(self.file_path):
                data = default_initial_state()
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

    def get_state(self) -> Dict[str, Any]:
        with self.lock:
            if not os.path.exists(self.file_path):
                return default_initial_state()
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return default_initial_state()

    def _save_state(self, state: Dict[str, Any]):
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def sync_epic(self, epic_name: str, goal: str, vertical_slices: List[Dict[str, Any]]) -> Dict[str, Any]:
        with self.lock:
            state = self.get_state()
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
                    "updated_at": time.strftime("%H:%M:%S")
                })
            state["nodes"] = nodes
            self._save_state(state)
        self._notify("EPIC_SYNCED", state["epic"])
        self._notify("STATE_FULL", state)
        return state

    def update_agent_pulse(self, pair_id: int, builder_status: str, critic_status: str,
                           slice_id: Optional[str] = None, attempt: Optional[int] = None,
                           details_md: Optional[str] = None) -> Dict[str, Any]:
        with self.lock:
            state = self.get_state()
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
                    elif builder_status == "WORKING":
                        node["kanban_status"] = "EXECUTING"
                    node["updated_at"] = time.strftime("%H:%M:%S")
            self._save_state(state)
        self._notify("PULSE_UPDATED", {"pair_id": pair_id, "builder": builder_status, "critic": critic_status})
        self._notify("STATE_FULL", state)
        return state

    def log_critique_verdict(self, slice_id: str, attempt: int, verdict: str,
                             reason_md: str) -> Dict[str, Any]:
        with self.lock:
            state = self.get_state()
            verdict_norm = "APROVADO" if "APROV" in verdict.upper() else "REJEITADO"
            entry = {
                "slice_id": slice_id,
                "attempt": attempt,
                "verdict": verdict_norm,
                "reason": reason_md,
                "timestamp": time.strftime("%H:%M:%S")
            }
            state.setdefault("gauntlet_log", []).append(entry)
            for node in state.get("nodes", []):
                if node["id"] == slice_id:
                    node["attempt"] = attempt
                    node["latest_feedback"] = f"[{verdict_norm}] {reason_md}"
                    node["kanban_status"] = "APPROVED" if verdict_norm == "APROVADO" else "REJEITADO"
                    node["updated_at"] = time.strftime("%H:%M:%S")
            self._save_state(state)
        self._notify("VERDICT_LOGGED", entry)
        self._notify("STATE_FULL", state)
        return entry

    def add_user_steering(self, text: str) -> Dict[str, Any]:
        with self.lock:
            state = self.get_state()
            msg = {
                "id": f"msg-{len(state.get('steering_messages', [])) + 1}",
                "sender": "USER",
                "text": text,
                "timestamp": time.strftime("%H:%M:%S"),
                "consumed": False
            }
            state.setdefault("steering_messages", []).append(msg)
            self._save_state(state)
        self._notify("STEERING_RECEIVED", msg)
        self._notify("STATE_FULL", state)
        return msg

    def fetch_unconsumed_steering(self) -> List[Dict[str, Any]]:
        with self.lock:
            state = self.get_state()
            unconsumed = [m for m in state.get("steering_messages", []) if not m.get("consumed", False)]
            for m in unconsumed:
                m["consumed"] = True
            if unconsumed:
                self._save_state(state)
        return unconsumed

    def post_orchestrator_message(self, text: str) -> Dict[str, Any]:
        with self.lock:
            state = self.get_state()
            msg = {
                "id": f"msg-{len(state.get('steering_messages', [])) + 1}",
                "sender": "ORCHESTRATOR",
                "text": text,
                "timestamp": time.strftime("%H:%M:%S"),
                "consumed": True
            }
            state.setdefault("steering_messages", []).append(msg)
            self._save_state(state)
        self._notify("ORCHESTRATOR_MESSAGE", msg)
        self._notify("STATE_FULL", state)
        return msg

    def get_metrics(self) -> Dict[str, Any]:
        with self.lock:
            state = self.get_state()
            nodes = state.get("nodes", [])
            logs = state.get("gauntlet_log", [])

            total_slices = len(nodes)
            approved_slices = len([n for n in nodes if n.get("kanban_status") == "APPROVED"])
            total_attempts = sum(n.get("attempt", 1) for n in nodes)
            first_pass_count = len([n for n in nodes if n.get("kanban_status") == "APPROVED" and n.get("attempt", 1) == 1])

            first_pass_rate = round((first_pass_count / approved_slices * 100), 1) if approved_slices > 0 else 0.0

            # Estimativa de tokens economizados pelo protocolo de ponteiros e descarregamento de contexto
            tokens_saved = (total_attempts * 3500) + (len(logs) * 1800) + 12000

            return {
                "total_slices": total_slices,
                "approved_slices": approved_slices,
                "total_attempts": total_attempts,
                "first_pass_rate": f"{first_pass_rate}%",
                "estimated_tokens_saved": f"{tokens_saved:,}".replace(",", "."),
                "gauntlet_verdicts_count": len(logs),
                "active_pairs_count": len([p for p in state.get("pairs_3x3", []) if p.get("builder_status") != "IDLE" or p.get("critic_status") != "IDLE"]),
                "last_update": time.strftime("%H:%M:%S")
            }

    def reset_state(self) -> Dict[str, Any]:
        with self.lock:
            state = default_initial_state()
            self._save_state(state)
        self._notify("STATE_RESET", state)
        self._notify("STATE_FULL", state)
        return state

db = StateStore()