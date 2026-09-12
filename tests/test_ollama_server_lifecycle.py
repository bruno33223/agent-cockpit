import os
import sys
import json
import time
import socket
import asyncio
import threading
import unittest
import urllib.request
import urllib.error
import uvicorn
import websockets
from unittest.mock import MagicMock, patch

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import web_server
from web_server import app, manager
from state_store import db


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestOllamaServerLifecycle(unittest.TestCase):
    server_thread = None
    server = None
    port = None
    base_url = None
    ws_url = None

    @classmethod
    def setUpClass(cls):
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.ws_url = f"ws://127.0.0.1:{cls.port}/ws"

        config = uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="error")
        cls.server = uvicorn.Server(config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()

        # Aguarda servidor iniciar
        started = False
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"{cls.base_url}/api/projects", timeout=1.0) as resp:
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

    def _http_get(self, endpoint):
        req = urllib.request.Request(f"{self.base_url}{endpoint}", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return resp.getcode(), data
        except urllib.error.HTTPError as e:
            data = json.loads(e.read().decode("utf-8"))
            return e.code, data

    def _http_post(self, endpoint, payload=None):
        data_bytes = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{endpoint}",
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return resp.getcode(), data
        except urllib.error.HTTPError as e:
            data = json.loads(e.read().decode("utf-8"))
            return e.code, data

    def test_01_rest_endpoints_exist_and_respond(self):
        """Verifica a existência e funcionamento dos endpoints REST do servidor Ollama."""
        # Teste de start-server (quando Ollama não está instalado, deve responder graciosamente sem 500)
        status_code, data = self._http_post("/api/local-worker/start-server")
        self.assertIn(status_code, [200, 400])
        self.assertIn("status", data)
        if data.get("status") == "ERROR":
            self.assertFalse(data.get("installed", True))
            self.assertIn("error", data)
        else:
            self.assertIn(data.get("status"), ["started", "already_running"])

        # Teste de start-server mockando inicialização com sucesso
        if web_server.ollama_process_manager:
            with patch.object(web_server.ollama_process_manager, "start", return_value={
                "status": "started",
                "running": True,
                "managed": True,
                "pid": 99999,
                "port": 11434,
                "message": "Subprocesso Ollama iniciado."
            }):
                status_code, data = self._http_post("/api/local-worker/start-server")
                self.assertEqual(status_code, 200)
                self.assertEqual(data.get("status"), "started")

        # Teste de server-logs
        status_code, data = self._http_get("/api/local-worker/server-logs")
        self.assertEqual(status_code, 200)
        self.assertIn("logs", data)
        self.assertIsInstance(data["logs"], list)
        self.assertIn("count", data)

        # Teste de stop-server
        status_code, data = self._http_post("/api/local-worker/stop-server")
        self.assertIn(status_code, [200, 400])
        self.assertIn("status", data)

    def test_02_server_lifecycle_autostart_logic(self):
        """Verifica a lógica de ciclo de vida e auto-start assíncrono em segundo plano."""
        self.assertTrue(hasattr(web_server, "auto_start_ollama_task"), "auto_start_ollama_task não definida no web_server")
        self.assertTrue(hasattr(web_server, "ollama_process_manager"), "ollama_process_manager global não definido no web_server")

        mock_mgr = MagicMock()
        mock_mgr.is_installed.return_value = True
        mock_mgr.is_port_open.return_value = False
        mock_mgr.managed_by_cockpit = True

        # Testa auto-start com auto_start_ollama = True
        with patch.object(web_server, "ollama_process_manager", mock_mgr):
            with patch.object(db, "get_local_worker_config", return_value={"auto_start_ollama": True}):
                asyncio.run(web_server.auto_start_ollama_task())
                self.assertTrue(mock_mgr.start.called, "start() deveria ser chamado quando auto_start_ollama=True e porta fechada")

        # Testa que NÃO inicia quando auto_start_ollama = False
        mock_mgr.reset_mock()
        with patch.object(web_server, "ollama_process_manager", mock_mgr):
            with patch.object(db, "get_local_worker_config", return_value={"auto_start_ollama": False}):
                asyncio.run(web_server.auto_start_ollama_task())
                self.assertFalse(mock_mgr.start.called, "start() não deveria ser chamado quando auto_start_ollama=False")

        # Testa que NÃO inicia quando a porta já estiver aberta
        mock_mgr.reset_mock()
        mock_mgr.is_port_open.return_value = True
        with patch.object(web_server, "ollama_process_manager", mock_mgr):
            with patch.object(db, "get_local_worker_config", return_value={"auto_start_ollama": True}):
                asyncio.run(web_server.auto_start_ollama_task())
                self.assertFalse(mock_mgr.start.called, "start() não deveria ser chamado se a porta já estiver aberta")

        # Testa shutdown
        if hasattr(web_server, "shutdown_event"):
            mock_mgr.reset_mock()
            mock_mgr.managed_by_cockpit = True
            with patch.object(web_server, "ollama_process_manager", mock_mgr):
                asyncio.run(web_server.shutdown_event())
                self.assertTrue(mock_mgr.stop.called, "stop() deveria ser chamado no shutdown se managed_by_cockpit=True")

    def test_03_websocket_broadcast_ollama_log(self):
        """Verifica o broadcast via WebSocket ao emitir evento de log do Ollama."""
        async def _test_ws():
            async with websockets.connect(self.ws_url) as ws:
                # Drena mensagens iniciais (PROJECTS_UPDATED, STATE_FULL)
                for _ in range(2):
                    msg_text = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    msg = json.loads(msg_text)

                # Dispara evento ollama_log através da função ou callback de log
                test_line = f"Test log entry at {time.time()}: Ollama server active."
                if hasattr(web_server, "_on_ollama_log"):
                    web_server._on_ollama_log(test_line)
                else:
                    manager.broadcast_sync("ollama_log", {"line": test_line})

                # Aguarda receber o evento ollama_log
                received_log = False
                for _ in range(5):
                    raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    data = json.loads(raw)
                    if data.get("event") == "ollama_log":
                        payload = data.get("payload", {})
                        if payload.get("line") == test_line:
                            received_log = True
                            break

                self.assertTrue(received_log, "Evento ollama_log com payload esperado não foi recebido via WebSocket")

        asyncio.run(_test_ws())


if __name__ == "__main__":
    unittest.main()
