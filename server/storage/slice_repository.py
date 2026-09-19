import os
import re
import time
import uuid
from typing import List, Dict, Any, Optional

def _generate_unique_msg_id(prefix: str = "msg") -> str:
    return f"{prefix}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"

class SliceRepository:
    """Gerencia o ciclo de vida de fatias verticais, pulses de agentes, steering e anomalias."""
    def __init__(self, facade: Any):
        self.facade = facade

    @property
    def lock(self):
        return self.facade.lock

    def sync_epic(self, epic_name: str, goal: str, vertical_slices: List[Dict[str, Any]],
                  project_root: Optional[str] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id, project_root)
        with self.lock:
            state = self.facade.get_state(target_pid)
            if project_root:
                state["project_root"] = os.path.abspath(project_root)
            state["epic"] = {
                "name": epic_name, "goal": goal, "status": "IN_PROGRESS",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            nodes = []
            for idx, s in enumerate(vertical_slices[:3], start=1):
                nodes.append({
                    "id": s.get("id", f"slice-{idx}"), "title": s.get("title", f"Fatia Vertical {idx}"),
                    "pair_id": idx, "kanban_status": "BACKLOG", "attempt": 1,
                    "max_attempts": s.get("max_attempts", 5),
                    "acceptance_criteria": s.get("acceptance_criteria", "Critérios definidos no blueprint."),
                    "spec_md": s.get("spec_md", "Especificação técnica."),
                    "latest_feedback": "Aguardando início da execução.", "tdd_stage": "PENDING",
                    "review_metrics": {"critical": 0, "important": 0, "minor": 0},
                    "updated_at": time.strftime("%H:%M:%S")
                })
            state["nodes"] = nodes
            if "local_worker" in state and isinstance(state["local_worker"], dict):
                state["local_worker"]["consecutive_failures"] = {}
            self.facade._save_state(state, target_pid)
            index_data = self.facade.project_repo._read_index()
            if index_data.get("current_project_id") == "default" and target_pid != "default":
                index_data["current_project_id"] = target_pid
                self.facade.project_repo._save_index(index_data)
        self.facade._notify("PROJECTS_UPDATED", self.facade.list_projects(), target_pid)
        self.facade._notify("EPIC_SYNCED", state["epic"], target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return state

    def update_agent_pulse(self, pair_id: int, builder_status: str, critic_status: str,
                           slice_id: Optional[str] = None, attempt: Optional[int] = None,
                           details_md: Optional[str] = None, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            for p in state.get("pairs_3x3", []):
                if p["id"] == pair_id:
                    p["builder_status"], p["critic_status"] = builder_status, critic_status
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
            self.facade._save_state(state, target_pid)
        self.facade._notify("PULSE_UPDATED", {"pair_id": pair_id, "builder": builder_status, "critic": critic_status}, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return state

    def set_slice_tdd_stage(self, slice_id: str, stage: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            for node in state.get("nodes", []):
                if node["id"] == slice_id:
                    node["tdd_stage"] = stage
                    node["updated_at"] = time.strftime("%H:%M:%S")
            self.facade._save_state(state, target_pid)
        self.facade._notify("TDD_STAGE_UPDATED", {"slice_id": slice_id, "stage": stage}, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return {"slice_id": slice_id, "tdd_stage": stage}

    def log_critique_verdict(self, slice_id: str, attempt: int, verdict: str,
                             reason_md: str, review_metrics: Optional[Dict[str, int]] = None,
                             project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            verdict_norm = "APROVADO" if any(k in verdict.upper() for k in ("APROV", "APPROV")) else "REJEITADO"
            metrics = review_metrics or {"critical": 0, "important": 0, "minor": 0}
            entry = {
                "slice_id": slice_id, "attempt": attempt, "verdict": verdict_norm,
                "reason": reason_md, "review_metrics": metrics, "timestamp": time.strftime("%H:%M:%S")
            }
            state.setdefault("gauntlet_log", []).append(entry)
            for node in state.get("nodes", []):
                if node["id"] == slice_id:
                    node["attempt"] = attempt
                    node["latest_feedback"] = f"[{verdict_norm}] {reason_md}"
                    node["kanban_status"] = "APPROVED" if verdict_norm == "APROVADO" else "REJEITADO"
                    node["review_metrics"] = metrics
                    node["updated_at"] = time.strftime("%H:%M:%S")
            self.facade._save_state(state, target_pid)
        self.facade._notify("VERDICT_LOGGED", entry, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return entry

    def add_user_steering(self, text: str, project_id: Optional[str] = None, slice_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        clean_slice = slice_id if slice_id and str(slice_id).strip() != "" and str(slice_id).lower() != "global" else None
        with self.lock:
            state = self.facade.get_state(target_pid)
            msg = {
                "id": _generate_unique_msg_id("msg"), "sender": "USER", "text": text,
                "timestamp": time.strftime("%H:%M:%S"), "consumed": False,
                "consumed_by": [], "slice_id": clean_slice
            }
            state.setdefault("steering_messages", []).append(msg)
            self.facade._save_state(state, target_pid)
        self.facade._notify("STEERING_RECEIVED", msg, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return msg

    def fetch_unconsumed_steering(self, project_id: Optional[str] = None, slice_id: Optional[str] = None) -> List[Dict[str, Any]]:
        target_pid = self.facade.resolve_project_id(project_id)
        clean_slice = slice_id if slice_id and str(slice_id).strip() != "" and str(slice_id).lower() != "global" else None
        with self.lock:
            state = self.facade.get_state(target_pid)
            unconsumed, modified = [], False
            for m in state.get("steering_messages", []):
                m_slice = m.get("slice_id")
                c_by = m.setdefault("consumed_by", [])
                if clean_slice is not None:
                    if m_slice == clean_slice and not m.get("consumed", False) and clean_slice not in c_by:
                        unconsumed.append(m)
                        m["consumed"] = True
                        c_by.append(clean_slice)
                        modified = True
                    elif m_slice is None and not m.get("consumed", False) and clean_slice not in c_by:
                        unconsumed.append(m)
                        c_by.append(clean_slice)
                        modified = True
                else:
                    if m_slice is None and not m.get("consumed", False):
                        unconsumed.append(m)
                        m["consumed"] = True
                        modified = True
            if modified:
                self.facade._save_state(state, target_pid)
        return unconsumed

    def post_orchestrator_message(self, text: str, project_id: Optional[str] = None, slice_id: Optional[str] = None, sender: str = "ORCHESTRATOR") -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        clean_slice = slice_id if slice_id and str(slice_id).strip() != "" and str(slice_id).lower() != "global" else None
        with self.lock:
            state = self.facade.get_state(target_pid)
            msg = {
                "id": _generate_unique_msg_id("msg"), "sender": sender or "ORCHESTRATOR", "text": text,
                "timestamp": time.strftime("%H:%M:%S"), "consumed": True,
                "consumed_by": [clean_slice] if clean_slice else [], "slice_id": clean_slice
            }
            state.setdefault("steering_messages", []).append(msg)
            self.facade._save_state(state, target_pid)
        self.facade._notify("ORCHESTRATOR_MESSAGE", msg, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return msg

    def get_slice_steering_messages(self, project_id: Optional[str] = None, slice_id: Optional[str] = None) -> List[Dict[str, Any]]:
        clean_slice = slice_id if slice_id and str(slice_id).strip() != "" and str(slice_id).lower() != "global" else None
        state = self.facade.get_state(self.facade.resolve_project_id(project_id))
        all_msgs = state.get("steering_messages", [])
        return [m for m in all_msgs if m.get("slice_id") == clean_slice] if clean_slice else [m for m in all_msgs if m.get("slice_id") is None]

    def get_slice_spec(self, slice_id: str, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        state = self.facade.get_state(self.facade.resolve_project_id(project_id))
        for node in state.get("nodes", []):
            if node.get("id") == slice_id or str(node.get("pair_id")) == str(slice_id):
                return {
                    "id": node.get("id"), "title": node.get("title"),
                    "acceptance_criteria": node.get("acceptance_criteria"), "spec_md": node.get("spec_md"),
                    "kanban_status": node.get("kanban_status"), "attempt": node.get("attempt", 1),
                    "max_attempts": node.get("max_attempts", 5), "tdd_stage": node.get("tdd_stage", "PENDING"),
                    "review_metrics": node.get("review_metrics", {"critical": 0, "important": 0, "minor": 0})
                }
        return None

    def prune_session_context(self, retain_last_messages: int = 3, retain_last_verdicts: int = 6,
                              project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            all_msgs = state.get("steering_messages", [])
            p_msgs = max(0, len(all_msgs) - retain_last_messages)
            if p_msgs > 0:
                summary = {"id": "msg-pruned-summary", "sender": "SYSTEM", "text": f"[CONTEXT_PRUNED] {p_msgs} mensagens consolidadas.", "timestamp": time.strftime("%H:%M:%S"), "consumed": True}
                state["steering_messages"] = [summary] + all_msgs[-retain_last_messages:]
            all_v = state.get("gauntlet_log", [])
            p_v = max(0, len(all_v) - retain_last_verdicts)
            if p_v > 0:
                state["gauntlet_log"] = all_v[-retain_last_verdicts:]
            for node in state.get("nodes", []):
                fb = node.get("latest_feedback", "")
                if len(fb) > 300:
                    node["latest_feedback"] = fb[:297] + "..."
            self.facade._save_state(state, target_pid)
        self.facade._notify("CONTEXT_PRUNED", {"pruned_messages": p_msgs, "pruned_verdicts": p_v, "timestamp": time.strftime("%H:%M:%S")}, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return {"status": "PRUNED", "project_id": target_pid, "epic_name": state.get("epic", {}).get("name"), "pruned_messages_count": p_msgs, "pruned_verdicts_count": p_v, "active_nodes_count": len(state.get("nodes", []))}

    def register_fleet_anomaly(self, slice_id: Optional[str], anomaly_type: str, details: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            target_slice = None
            for n in state.get("nodes", []):
                if (slice_id and n.get("id") == slice_id) or (not slice_id and n.get("kanban_status") in ["EXECUTING", "REVIEWING"]):
                    n["kanban_status"] = "BLOCKED_NO_CREDIT" if anomaly_type == "OUT_OF_CREDITS" else "STALLED"
                    n["latest_feedback"] = f"⚠️ ANOMALIA [{anomaly_type}]: {details}"
                    target_slice = n.get("id")
                    break
            for p in state.get("pairs_3x3", []):
                if not target_slice or p.get("current_slice_id") == target_slice:
                    p["builder_status"], p["critic_status"] = "BLOCKED", "IDLE"
            state.setdefault("steering_messages", []).append({
                "id": _generate_unique_msg_id("msg-err"), "sender": "ORCHESTRATOR",
                "text": f"🚨 ALERTA DE SISTEMA [{anomaly_type}]: {details}.", "timestamp": time.strftime("%H:%M:%S"),
                "consumed": False, "consumed_by": [target_slice] if target_slice else [], "slice_id": target_slice
            })
            self.facade._save_state(state, target_pid)
            cp_path = self.facade.project_repo.freeze_checkpoint(state, target_pid)
        self.facade._notify("FLEET_ANOMALY", {"anomaly_type": anomaly_type, "slice_id": target_slice, "details": details}, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return {"status": "ANOMALY_REGISTERED", "anomaly_type": anomaly_type, "affected_slice": target_slice, "checkpoint_path": cp_path, "details": details}

    def check_fleet_liveness(self, subagents_status: Optional[List[Dict[str, Any]]] = None,
                             repo_root: Optional[str] = None, slice_id: Optional[str] = None,
                             project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        state = self.facade.get_state(target_pid)
        root = repo_root or state.get("project_root")
        if subagents_status:
            kws = ["resourceexhausted", "quota", "credit", "rate limit", "insufficient_quota", "billing", "exceeded"]
            for sub in subagents_status:
                s_state, s_detail = str(sub.get("state", "")).lower(), str(sub.get("stateDetail", "")).lower()
                if any(kw in s_detail for kw in kws) or (s_state == "errored" and "quota" in s_detail):
                    anom = self.register_fleet_anomaly(slice_id=slice_id, anomaly_type="OUT_OF_CREDITS", details=f"Subagente '{sub.get('role', sub.get('conversationId'))}' esgotou créditos: {sub.get('stateDetail')}", project_id=target_pid)
                    return {"healthy": False, "anomaly_type": "OUT_OF_CREDITS", "details": anom["details"], "checkpoint_path": anom["checkpoint_path"]}
        if root and slice_id:
            proof = self.facade.project_repo.verify_worktree_commit_proof(root, slice_id)
            if not proof.get("valid_proof"):
                anom = self.register_fleet_anomaly(slice_id=slice_id, anomaly_type="ZERO_COMMIT_DROPPED", details=f"Proof of Work falhou: {proof.get('reason')}", project_id=target_pid)
                return {"healthy": False, "anomaly_type": "ZERO_COMMIT_DROPPED", "details": proof.get("reason"), "checkpoint_path": anom["checkpoint_path"]}
        return {"healthy": True, "anomaly_type": None, "message": "Frota íntegra. Nenhuma falha detectada."}

    def resume_orchestration(self, project_id: Optional[str] = None, project_root: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id, project_root)
        with self.lock:
            state = self.facade.get_state(target_pid)
            resumed = []
            for n in state.get("nodes", []):
                if n.get("kanban_status") in ["BLOCKED_NO_CREDIT", "STALLED"]:
                    n["kanban_status"], n["latest_feedback"] = "EXECUTING", "Retomada autorizada após verificação."
                    resumed.append(n.get("id"))
            for p in state.get("pairs_3x3", []):
                if p.get("builder_status") == "BLOCKED":
                    p["builder_status"] = "IDLE"
            self.facade._save_state(state, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return {
            "status": "RESUMED", "project_id": target_pid, "resumed_slices": resumed,
            "approved_slices": [n.get("id") for n in state.get("nodes", []) if n.get("kanban_status") == "APPROVED"],
            "pending_slices": [n.get("id") for n in state.get("nodes", []) if n.get("kanban_status") != "APPROVED"]
        }
