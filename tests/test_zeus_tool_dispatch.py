"""
tests/test_zeus_tool_dispatch.py: Suíte TDD para a Issue #44:
Chief Architect: Function Calling Tático, Despacho de Workers e Telemetria de Estados WebSocket.
"""

import os
import sys
import time
import json
import uuid
import unittest
from unittest.mock import patch, MagicMock

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)


class TestZeusToolDispatch(unittest.TestCase):
    """Testes para o motor Zeus Chief Architect, despacho de ferramentas e telemetria."""

    @classmethod
    def setUpClass(cls):
        cls.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.zeus_engine_path = os.path.join(cls.base_dir, "server", "chat", "zeus_engine.py")
        cls.zeus_chat_router_path = os.path.join(cls.base_dir, "server", "routers", "zeus_chat.py")
        cls.test_file_path = os.path.abspath(__file__)

    def test_01_line_count_guardrails(self):
        """Critério 1 & 2 & 3: Guardrails estritos de contagem de linhas."""
        with open(self.zeus_engine_path, "r", encoding="utf-8") as f:
            engine_lines = len(f.readlines())
        with open(self.zeus_chat_router_path, "r", encoding="utf-8") as f:
            router_lines = len(f.readlines())
        with open(self.test_file_path, "r", encoding="utf-8") as f:
            test_lines = len(f.readlines())

        self.assertLessEqual(
            engine_lines, 250,
            f"zeus_engine.py tem {engine_lines} linhas; limite estrito é <= 250"
        )
        self.assertLessEqual(
            router_lines, 250,
            f"zeus_chat.py tem {router_lines} linhas; limite estrito é <= 250"
        )
        self.assertLessEqual(
            test_lines, 400,
            f"test_zeus_tool_dispatch.py tem {test_lines} linhas; limite estrito é <= 400"
        )

    def test_02_chief_architect_system_prompt_and_tool_catalog(self):
        """Critério 1: Prompt do Arquiteto Chefe e Catálogo de Ferramentas Function Calling."""
        from server.chat.constants import DEFAULT_ZEUS_SYSTEM_PROMPT, AVAILABLE_TOOLS

        prompt_lower = DEFAULT_ZEUS_SYSTEM_PROMPT.lower()
        # Papel de liderança e orquestrador staff
        self.assertTrue(
            "arquiteto" in prompt_lower or "orchestrator" in prompt_lower or "orquestrador" in prompt_lower,
            "Prompt deve definir o papel de Arquiteto/Orquestrador Chefe."
        )
        # Visão sistêmica ou diálogo de alto nível
        self.assertTrue(
            "alto nível" in prompt_lower or "visão sistêmica" in prompt_lower or "sistêmica" in prompt_lower or "planejamento" in prompt_lower,
            "Prompt deve orientar visão sistêmica e diálogo de alto nível."
        )
        # Proibição de codificar diretamente no chat
        self.assertTrue(
            "não codificar diretamente" in prompt_lower or "nunca tente resolver" in prompt_lower or "sem codificar" in prompt_lower or "não codifique" in prompt_lower,
            "Prompt deve proibir codificação direta no chat principal sem delegar."
        )

        # Catálogo de ferramentas
        tool_names = [
            t.get("function", {}).get("name")
            for t in AVAILABLE_TOOLS
            if isinstance(t, dict) and "function" in t
        ]
        self.assertIn("dispatch_subagent", tool_names, "Tool dispatch_subagent deve constar em AVAILABLE_TOOLS.")
        self.assertIn("run_test_suite", tool_names, "Tool run_test_suite deve constar em AVAILABLE_TOOLS.")
        self.assertIn("read_project_status", tool_names, "Tool read_project_status deve constar em AVAILABLE_TOOLS.")

    @patch("server.chat.tool_dispatcher.create_slice_worktree")
    @patch("server.chat.tool_dispatcher.local_worker_queue")
    def test_03_dispatch_subagent_tool(self, mock_queue, mock_worktree):
        """Critério 1.a: dispatch_subagent cria worktree e enfileira na WorkerQueue."""
        from server.chat.tool_dispatcher import dispatch_subagent

        mock_worktree.return_value = {
            "status": "CREATED",
            "worktree_path": ".worktrees/slice-auth",
            "branch": "cockpit/slice-auth"
        }
        mock_queue.enqueue.return_value = "ticket-auth123"

        result = dispatch_subagent(
            task_description="Implementar autenticação JWT com refresh tokens",
            target_slice="slice-auth",
            isolation_level="worktree"
        )

        self.assertEqual(result.get("status"), "queued")
        self.assertEqual(result.get("ticket_id"), "ticket-auth123")
        self.assertEqual(result.get("slice_id"), "slice-auth")
        self.assertEqual(result.get("isolation_level"), "worktree")
        mock_worktree.assert_called_once()
        mock_queue.enqueue.assert_called_once()

    @patch("server.chat.tool_dispatcher.run_distilled_tests")
    def test_04_run_test_suite_tool(self, mock_distilled):
        """Critério 1.a: run_test_suite executa testes via test_runner."""
        from server.chat.tool_dispatcher import run_test_suite

        mock_distilled.return_value = {
            "status": "PASSED",
            "command": "pytest tests/test_auth.py",
            "duration_seconds": 1.25,
            "exit_code": 0,
            "failures_count": 0,
            "failures": []
        }

        res = run_test_suite(test_target="tests/test_auth.py", run_mode="fast")
        self.assertEqual(res.get("status"), "PASSED")
        self.assertEqual(res.get("exit_code"), 0)
        self.assertEqual(res.get("failures_count"), 0)
        mock_distilled.assert_called_once()

    @patch("server.chat.tool_dispatcher.db")
    def test_05_read_project_status_tool(self, mock_db):
        """Critério 1.a: read_project_status retorna sumário consolidado do projeto."""
        from server.chat.tool_dispatcher import read_project_status

        mock_db.get_current_project_id.return_value = "proj-alpha"
        mock_db.get_state.return_value = {
            "project_id": "proj-alpha",
            "epic": {"name": "Épico Teste", "status": "IN_PROGRESS"},
            "slices": [
                {"id": "slice-1", "title": "Setup", "status": "DONE"},
                {"id": "slice-2", "title": "API", "status": "IN_PROGRESS"}
            ],
            "gates": {"gate_ship_approved": True}
        }

        status = read_project_status(project_id="proj-alpha")
        self.assertEqual(status.get("project_id"), "proj-alpha")
        self.assertIn("slices_summary", status)
        self.assertEqual(status["slices_summary"].get("total"), 2)
        self.assertEqual(status["slices_summary"].get("done"), 1)
        self.assertEqual(status["slices_summary"].get("in_progress"), 1)
        self.assertIn("epic", status)

    def test_06_avatar_telemetry_event_format_and_emission(self):
        """Critério 1 & 3.b: Emissão e formato estruturado dos eventos de avatar."""
        from server.chat.avatar_telemetry import (
            emit_avatar_state,
            AVATAR_STATES,
            LISTENING,
            THINKING,
            DISPATCHING_WORKER,
            TESTING,
            SPEAKING
        )

        expected = [LISTENING, THINKING, DISPATCHING_WORKER, TESTING, SPEAKING]
        for st in expected:
            self.assertIn(st, AVATAR_STATES)

        received_events = []

        def mock_broadcast(event_type, payload, project_id=None):
            received_events.append((event_type, payload, project_id))

        event = emit_avatar_state(
            state=DISPATCHING_WORKER,
            session_id="sess-42",
            broadcast_callback=mock_broadcast,
            project_id="proj-test",
            extra={"worker_task": "task-abc"}
        )

        self.assertEqual(event.get("type"), "avatar_state")
        self.assertEqual(event.get("state"), DISPATCHING_WORKER)
        self.assertEqual(event.get("session_id"), "sess-42")
        self.assertIn("timestamp", event)
        self.assertEqual(event.get("worker_task"), "task-abc")

        # Valida chamada ao broadcast WebSocket
        self.assertEqual(len(received_events), 1)
        b_type, b_payload, b_pid = received_events[0]
        self.assertEqual(b_type, "AVATAR_STATE")
        self.assertEqual(b_payload.get("state"), DISPATCHING_WORKER)
        self.assertEqual(b_pid, "proj-test")

    def test_07_zeus_engine_chat_stream_avatar_events(self):
        """Critério 1: zeus_engine emite eventos de avatar no fluxo stream_chat."""
        from server.chat.zeus_engine import ZeusChatEngine

        engine = ZeusChatEngine()
        ws_events = []

        def mock_ws(event_type, payload, pid=None):
            ws_events.append((event_type, payload))

        # Executa stream usando fallback
        events = list(engine.stream_chat(
            session_id="test-session-stream",
            message="Status do projeto e rodar testes da aplicação",
            backend="fallback",
            broadcast_callback=mock_ws
        ))

        event_types = [e.get("type") for e in events]
        self.assertIn("avatar_state", event_types, "Stream deve conter eventos de avatar_state.")

        avatar_states_emitted = [
            e.get("state") for e in events if e.get("type") == "avatar_state"
        ]
        # Deve ter emitido pelo menos LISTENING ou THINKING e SPEAKING
        self.assertTrue(
            any(s in avatar_states_emitted for s in ["LISTENING", "THINKING"]),
            "Avatar deve emitir LISTENING ou THINKING no início."
        )
        self.assertIn("SPEAKING", avatar_states_emitted, "Avatar deve emitir SPEAKING ao gerar conteúdo.")

    @patch("server.routers.orchestrator.db")
    @patch("server.routers.orchestrator.manager")
    def test_08_worker_completion_natural_language_notification(self, mock_mgr, mock_db):
        """Critério 2 & 3.c: Notificação de conclusão de tarefas da WorkerQueue em PT-BR."""
        from server.routers.orchestrator import notify_worker_task_completion

        task_data = {
            "ticket_id": "ticket-xyz789",
            "slice_id": "slice-db-migration",
            "status": "completed",
            "duration": 4.5,
            "tokens": 1250,
            "error": None
        }

        msg = notify_worker_task_completion(task_data, project_id="proj-omega")
        self.assertIsNotNone(msg)
        self.assertIn("slice-db-migration", msg.get("text", ""))
        self.assertIn("concluída com sucesso", msg.get("text", "").lower())
        self.assertIn("4.5", msg.get("text", ""))

        # Notificação de erro
        task_error = {
            "ticket_id": "ticket-err1",
            "slice_id": "slice-payment",
            "status": "error",
            "duration": 1.2,
            "tokens": 100,
            "error": "SyntaxError: invalid token"
        }
        msg_err = notify_worker_task_completion(task_error, project_id="proj-omega")
        self.assertIn("slice-payment", msg_err.get("text", ""))
        self.assertTrue(
            "falhou" in msg_err.get("text", "").lower() or "erro" in msg_err.get("text", "").lower()
        )
        mock_db.post_orchestrator_message.assert_called()

    @patch("server.chat.tool_dispatcher.execute_zeus_tool")
    def test_09_tool_dispatch_router_endpoint(self, mock_exec):
        """Critério 2: Endpoint /api/zeus-chat/tool-dispatch despacha ferramentas táticas."""
        from server.routers.zeus_chat import post_zeus_tool_dispatch_endpoint

        mock_exec.return_value = {"status": "ok", "project_id": "proj-1"}
        payload = {"tool": "read_project_status", "params": {}, "project_id": "proj-1"}
        res = post_zeus_tool_dispatch_endpoint(payload)
        self.assertEqual(res.get("status"), "ok")
        mock_exec.assert_called_once()

    @patch("server.routers.zeus_chat.notify_worker_task_completion")
    def test_10_zeus_chat_worker_queue_listener(self, mock_notify):
        """Critério 2: Callback de worker queue notifica tarefas finalizadas."""
        from server.routers.zeus_chat import _on_worker_queue_update, _notified_worker_tickets

        unique_tid = f"ticket-test-{uuid.uuid4().hex[:6]}"
        status_payload = {
            "history": [{
                "ticket_id": unique_tid,
                "slice_id": "slice-notif",
                "status": "completed",
                "duration": 3.0,
                "tokens": 400
            }]
        }
        _on_worker_queue_update(status_payload)
        self.assertIn(unique_tid, _notified_worker_tickets)
        mock_notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
