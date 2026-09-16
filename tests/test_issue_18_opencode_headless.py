import os
import sys
import json
import time
import socket
import threading
import unittest
import urllib.request
import urllib.error
import uvicorn

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
WORKTREE_ROOT = os.path.abspath(os.path.join(TESTS_DIR, ".."))
SERVER_DIR = os.path.join(WORKTREE_ROOT, "server")

if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
if WORKTREE_ROOT not in sys.path:
    sys.path.insert(0, WORKTREE_ROOT)

import opencode_manager
from web_server import app, manager as ws_manager


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestOpenCodeHeadlessManager(unittest.TestCase):
    def setUp(self):
        # Garante nova instância ou estado limpo para testes
        if hasattr(opencode_manager, "OpenCodeManager"):
            self.manager = opencode_manager.OpenCodeManager()
        else:
            self.manager = opencode_manager

    def test_headless_session_lifecycle_non_blocking(self):
        """Verifica que start_headless_session, send_headless_message e get_headless_status funcionam sem bloquear threads."""
        t0 = time.time()
        session_info = self.manager.start_headless_session(
            session_id="test-session-1",
            prompt="Hello headless OpenCode",
            cwd=WORKTREE_ROOT,
            model="auto"
        )
        elapsed = time.time() - t0
        self.assertLess(elapsed, 1.0, "start_headless_session deve retornar imediatamente sem bloquear a thread")
        self.assertIsInstance(session_info, dict)
        self.assertEqual(session_info.get("session_id"), "test-session-1")
        self.assertIn(session_info.get("status"), ["started", "running", "idle", "active"])

        # Status check
        status = self.manager.get_headless_status("test-session-1")
        self.assertIsInstance(status, dict)
        self.assertEqual(status.get("session_id"), "test-session-1")
        self.assertTrue(status.get("running") is not None or status.get("status") is not None)

        # Send message
        t0 = time.time()
        msg_res = self.manager.send_headless_message(
            session_id="test-session-1",
            message="Execute background task"
        )
        elapsed = time.time() - t0
        self.assertLess(elapsed, 1.0, "send_headless_message deve despachar sem bloquear o servidor")
        self.assertIsInstance(msg_res, dict)
        self.assertEqual(msg_res.get("status"), "sent")

    def test_subagent_lifecycle_and_tracking(self):
        """Verifica detecção e registro do ciclo de vida de subagentes com ID, role e terminal/stream."""
        # Registra subagente 1
        subagent = self.manager.register_subagent(
            parent_session_id="test-session-1",
            subagent_id="sub-builder-1",
            role="builder",
            task="Criar fatia 1",
            terminal_id="term-sub-1",
            stream_id="stream-sub-1"
        )
        self.assertIsInstance(subagent, dict)
        self.assertEqual(subagent.get("subagent_id"), "sub-builder-1")
        self.assertEqual(subagent.get("role"), "builder")
        self.assertEqual(subagent.get("terminal_id"), "term-sub-1")
        self.assertEqual(subagent.get("stream_id"), "stream-sub-1")

        # Lista subagentes
        subagents = self.manager.list_subagents(parent_session_id="test-session-1")
        self.assertIsInstance(subagents, list)
        self.assertTrue(any(s.get("subagent_id") == "sub-builder-1" for s in subagents))

        # Busca subagente individual
        found = self.manager.get_subagent("sub-builder-1")
        self.assertIsNotNone(found)
        self.assertEqual(found.get("role"), "builder")


class TestOpenCodeHeadlessAPI(unittest.TestCase):
    server_thread = None
    server = None
    port = None
    base_url = None

    @classmethod
    def setUpClass(cls):
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        config = uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="error")
        cls.server = uvicorn.Server(config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()

        started = False
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"{cls.base_url}/api/health", timeout=1.0) as resp:
                    if resp.getcode() == 200:
                        started = True
                        break
            except Exception:
                time.sleep(0.1)

        if not started:
            raise RuntimeError("Não foi possível iniciar o servidor de testes uvicorn.")

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.should_exit = True
        if cls.server_thread:
            cls.server_thread.join(timeout=3.0)

    def test_api_headless_endpoints_and_websocket_events(self):
        """Verifica /api/opencode/headless/start, /message e /subagents retornando status 200 com payload estruturado e eventos."""
        events_captured = []
        original_broadcast_sync = ws_manager.broadcast_sync

        def mock_broadcast_sync(event_type: str, payload: dict, project_id=None):
            events_captured.append((event_type, payload))
            try:
                original_broadcast_sync(event_type, payload, project_id)
            except Exception:
                pass

        ws_manager.broadcast_sync = mock_broadcast_sync

        try:
            # 1. POST /api/opencode/headless/start
            start_payload = json.dumps({
                "session_id": "api-session-100",
                "prompt": "Iniciar orquestração headless",
                "model": "auto"
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/opencode/headless/start",
                data=start_payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                self.assertEqual(resp.getcode(), 200)
                res_data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(res_data.get("status"), "ok")
                self.assertEqual(res_data.get("session_id"), "api-session-100")

            # 2. POST /api/opencode/headless/message
            msg_payload = json.dumps({
                "session_id": "api-session-100",
                "message": "Mensagem para o agente headless"
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/opencode/headless/message",
                data=msg_payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                self.assertEqual(resp.getcode(), 200)
                res_data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(res_data.get("status"), "ok")

            # Verifica se evento WebSocket OPENCODE_CHAT_MESSAGE foi emitido
            chat_events = [e for e in events_captured if e[0] == "OPENCODE_CHAT_MESSAGE"]
            self.assertTrue(len(chat_events) > 0, "Evento OPENCODE_CHAT_MESSAGE deve ser emitido no WebSocket")

            # Registra um subagente via manager diretamente para validar o endpoint GET
            if hasattr(opencode_manager, "register_subagent"):
                opencode_manager.register_subagent(
                    parent_session_id="api-session-100",
                    subagent_id="sub-reviewer-1",
                    role="critic",
                    terminal_id="term-sub-reviewer"
                )

            # 3. GET /api/opencode/headless/subagents
            req = urllib.request.Request(f"{self.base_url}/api/opencode/headless/subagents?session_id=api-session-100")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                self.assertEqual(resp.getcode(), 200)
                res_data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(res_data.get("status"), "ok")
                self.assertIn("subagents", res_data)
                self.assertIsInstance(res_data["subagents"], list)

        finally:
            ws_manager.broadcast_sync = original_broadcast_sync


if __name__ == "__main__":
    unittest.main()
