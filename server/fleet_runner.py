"""
server/fleet_runner.py
Runner de Orquestração Autônoma de Frotas 3x3 com Ciclo Gauntlet (Builder vs Harsh Critic).
Mapeado na Issue #41 / GAP 3: Frotas de Subagentes, Pipeline de 2 Tempos e Sincronização DAG.
"""

import sys
import os
from typing import Any, Callable, Dict, List, Optional

_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

from storage import StateFacade


class GauntletFleetRunner:
    """
    Orquestrador interno autônomo de frotas 3x3 no Agent Cockpit.
    Executa fatias verticais no pipeline de 2 tempos (Tempo 1: Builder -> Tempo 2: Harsh Critic).
    """

    def __init__(self, state_facade: Optional[StateFacade] = None):
        if state_facade is not None:
            self.facade = state_facade
        else:
            from state_store import db
            self.facade = db

    def _resolve_pair_id(self, slice_id: str, node: Optional[Dict[str, Any]] = None) -> int:
        if node and node.get("pair_id"):
            try:
                return int(node["pair_id"])
            except (ValueError, TypeError):
                pass
        if "-" in slice_id:
            try:
                return int(slice_id.split("-")[-1])
            except (ValueError, TypeError):
                pass
        return 1

    def step_slice(
        self,
        project_id: str,
        slice_id: str,
        builder_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        critic_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Executa um passo no ciclo de vida de uma fatia específica em 2 tempos:
        Tempo 1: Builder implementa o código e entrega artefatos/diff.
        Tempo 2: Harsh Critic audita o trabalho e emite veredito APROVADO/REJEITADO.
        """
        target_pid = self.facade.resolve_project_id(project_id)
        state = self.facade.get_state(target_pid)
        node = next((n for n in state.get("nodes", []) if n.get("id") == slice_id), None)

        if not node:
            return {
                "slice_id": slice_id,
                "status": "ERROR",
                "message": f"Fatia '{slice_id}' não encontrada no projeto '{target_pid}'.",
                "approved": False,
            }

        if node.get("kanban_status") == "APPROVED":
            return {
                "slice_id": slice_id,
                "status": "ALREADY_APPROVED",
                "approved": True,
                "verdict": "APROVADO",
            }

        pair_id = self._resolve_pair_id(slice_id, node)
        attempt = node.get("attempt", 1)
        max_attempts = node.get("max_attempts", 5)
        spec = self.facade.get_slice_spec(slice_id, project_id=target_pid) or {}

        # ==================== TEMPO 1: BUILDER ====================
        self.facade.update_agent_pulse(
            pair_id=pair_id,
            builder_status="WORKING",
            critic_status="IDLE",
            slice_id=slice_id,
            attempt=attempt,
            details_md="Builder executando implementação da fatia vertical...",
            project_id=target_pid,
        )

        try:
            if builder_fn:
                builder_output = builder_fn(target_pid, slice_id, attempt, spec)
            else:
                builder_output = {
                    "status": "COMPLETED",
                    "output": f"Implementação gerada pelo builder para {slice_id}",
                }
        except Exception as err:
            builder_output = {"status": "FAILED", "error": str(err)}

        # Transição de sincronização Builder -> Critic
        self.facade.update_agent_pulse(
            pair_id=pair_id,
            builder_status="WAITING",
            critic_status="REVIEWING",
            slice_id=slice_id,
            attempt=attempt,
            details_md="Builder concluiu entrega. Harsh Critic auditando...",
            project_id=target_pid,
        )

        # ==================== TEMPO 2: HARSH CRITIC ====================
        try:
            if critic_fn:
                critic_res = critic_fn(target_pid, slice_id, attempt, builder_output, spec)
            else:
                critic_res = {
                    "verdict": "APROVADO",
                    "reason_md": "Auditoria de qualidade aprovada com sucesso.",
                    "review_metrics": {"critical": 0, "important": 0, "minor": 0},
                }
        except Exception as err:
            critic_res = {
                "verdict": "REJEITADO",
                "reason_md": f"Falha na auditoria do Harsh Critic: {err}",
                "review_metrics": {"critical": 1, "important": 0, "minor": 0},
            }

        verdict_raw = critic_res.get("verdict", "REJEITADO")
        is_approved = any(k in verdict_raw.upper() for k in ("APROV", "APPROV"))
        verdict = "APROVADO" if is_approved else "REJEITADO"
        reason_md = critic_res.get("reason_md", "Veredito da banca revisora Gauntlet.")
        review_metrics = critic_res.get("review_metrics", {"critical": 0, "important": 0, "minor": 0})

        # Registra formalmente o veredito no gauntlet_log e atualiza Kanban
        self.facade.log_critique_verdict(
            slice_id=slice_id,
            attempt=attempt,
            verdict=verdict,
            reason_md=reason_md,
            review_metrics=review_metrics,
            project_id=target_pid,
        )

        if is_approved:
            builder_pulse = "IDLE"
            critic_pulse = "APPROVED"
            next_attempt = attempt
            node_status = "APPROVED"
        else:
            builder_pulse = "WORKING"
            critic_pulse = "REJECTED"
            next_attempt = attempt + 1 if attempt < max_attempts else attempt
            node_status = "REJEITADO"

        self.facade.update_agent_pulse(
            pair_id=pair_id,
            builder_status=builder_pulse,
            critic_status=critic_pulse,
            slice_id=slice_id,
            attempt=next_attempt,
            details_md=f"[{verdict}] {reason_md}",
            project_id=target_pid,
        )

        with self.facade.lock:
            st_upd = self.facade.get_state(target_pid)
            for n in st_upd.get("nodes", []):
                if n.get("id") == slice_id:
                    n["kanban_status"] = node_status
                    n["attempt"] = next_attempt
            self.facade._save_state(st_upd, target_pid)

        return {
            "slice_id": slice_id,
            "pair_id": pair_id,
            "attempt": attempt,
            "verdict": verdict,
            "approved": is_approved,
            "builder_output": builder_output,
            "critic_feedback": reason_md,
            "review_metrics": review_metrics,
        }

    def run_fleet_cycle(
        self,
        project_id: str,
        max_iterations: int = 5,
        slice_ids: Optional[List[str]] = None,
        builder_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        critic_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Orquestra autonomamente o ciclo de vida completo da frota 3x3 de ponta a ponta.
        Executa iterações até que todas as fatias sejam APROVADAS ou atinjam o teto de iterações.
        """
        target_pid = self.facade.resolve_project_id(project_id)
        target_slices = slice_ids or ["slice-1", "slice-2", "slice-3"]
        iteration = 0
        all_approved = False

        while iteration < max_iterations:
            iteration += 1
            state = self.facade.get_state(target_pid)
            active_nodes = {n["id"]: n for n in state.get("nodes", []) if n.get("id") in target_slices}

            pending_slices = [
                sid
                for sid in target_slices
                if active_nodes.get(sid, {}).get("kanban_status") != "APPROVED"
            ]

            if not pending_slices:
                all_approved = True
                break

            for sid in pending_slices:
                self.step_slice(
                    project_id=target_pid,
                    slice_id=sid,
                    builder_fn=builder_fn,
                    critic_fn=critic_fn,
                )

            # Reavalia estado pós-rodada
            state_after = self.facade.get_state(target_pid)
            remaining = [
                sid
                for sid in target_slices
                if next(
                    (n for n in state_after.get("nodes", []) if n.get("id") == sid),
                    {},
                ).get("kanban_status")
                != "APPROVED"
            ]

            if not remaining:
                all_approved = True
                break

        final_state = self.facade.get_state(target_pid)
        approved_nodes = [
            n
            for n in final_state.get("nodes", [])
            if n.get("id") in target_slices and n.get("kanban_status") == "APPROVED"
        ]

        return {
            "project_id": target_pid,
            "iterations": iteration,
            "all_approved": all_approved,
            "total_slices": len(target_slices),
            "approved_slices_count": len(approved_nodes),
            "slices": {
                n["id"]: {
                    "kanban_status": n.get("kanban_status"),
                    "attempt": n.get("attempt", 1),
                }
                for n in final_state.get("nodes", [])
                if n.get("id") in target_slices
            },
            "verdicts_logged": len(final_state.get("gauntlet_log", [])),
        }
