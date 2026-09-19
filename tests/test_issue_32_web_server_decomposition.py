"""
test_issue_32_web_server_decomposition.py: Testes para a Issue #32.
Valida a decomposição de server/web_server.py em APIRouters modulares em server/routers/:
- server/web_server.py < 200 linhas
- cada arquivo em server/routers/ <= 300 linhas
- montagem dos roteadores na aplicação FastAPI app
- validação funcional de endpoints representativos e WebSocket /ws
- exportação e compatibilidade de utilitários
"""

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
import websockets
import uvicorn

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_DIR = os.path.join(REPO_ROOT, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import server.web_server as web_server
from server.web_server import app


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class TestIssue32WebServerDecomposition(unittest.TestCase):
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

    def _http_get(self, endpoint: str):
        req = urllib.request.Request(f"{self.base_url}{endpoint}", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return resp.getcode(), data
        except urllib.error.HTTPError as e:
            try:
                data = json.loads(e.read().decode("utf-8"))
            except Exception:
                data = {"error": str(e)}
            return e.code, data

    def _http_post(self, endpoint: str, payload: dict = None):
        data_bytes = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{endpoint}",
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return resp.getcode(), data
        except urllib.error.HTTPError as e:
            try:
                data = json.loads(e.read().decode("utf-8"))
            except Exception:
                data = {"error": str(e)}
            return e.code, data

    def test_01_web_server_sloc_under_200(self):
        """Critério 2: server/web_server.py deve possuir menos de 200 linhas de código."""
        web_server_path = os.path.join(SERVER_DIR, "web_server.py")
        self.assertTrue(os.path.exists(web_server_path), "server/web_server.py não encontrado")
        with open(web_server_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        line_count = len(lines)
        self.assertLess(
            line_count,
            200,
            f"server/web_server.py tem {line_count} linhas, deve ter menos de 200 linhas",
        )

    def test_02_routers_sloc_and_structure(self):
        """Critério 1: cada roteador modular em server/routers/ deve ter <= 300 linhas."""
        routers_dir = os.path.join(SERVER_DIR, "routers")
        self.assertTrue(
            os.path.isdir(routers_dir),
            f"Diretório server/routers/ deve existir: {routers_dir}",
        )

        expected_routers = [
            "__init__.py",
            "telemetry.py",
            "settings.py",
            "omniroute.py",
            "models.py",
            "pty.py",
            "orchestrator.py",
            "zeus_chat.py",
        ]

        for router_file in expected_routers:
            path = os.path.join(routers_dir, router_file)
            self.assertTrue(
                os.path.exists(path),
                f"Arquivo de roteador obrigatório ausente: {router_file}",
            )
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            line_count = len(lines)
            self.assertLessEqual(
                line_count,
                300,
                f"server/routers/{router_file} tem {line_count} linhas, deve ter <= 300 linhas",
            )

    def test_03_routers_mounted_in_fastapi_app(self):
        """Verifica se os roteadores APIRouter existem no pacote server.routers e estão montados na app."""
        import server.routers as routers
        from fastapi import APIRouter

        router_modules = [
            "telemetry",
            "settings",
            "omniroute",
            "models",
            "pty",
            "orchestrator",
            "zeus_chat",
        ]

        for mod_name in router_modules:
            self.assertTrue(
                hasattr(routers, mod_name),
                f"Módulo server.routers.{mod_name} não exportado no pacote",
            )
            mod = getattr(routers, mod_name)
            self.assertTrue(
                hasattr(mod, "router"),
                f"server.routers.{mod_name} não possui atributo 'router'",
            )
            self.assertIsInstance(
                mod.router,
                APIRouter,
                f"server.routers.{mod_name}.router deve ser instância de APIRouter",
            )

    def test_04_functional_endpoints_representative(self):
        """Validação funcional de endpoints REST representativos de cada roteador."""
        # 1. Telemetry
        code, data = self._http_get("/api/health")
        self.assertEqual(code, 200)
        self.assertEqual(data.get("status"), "healthy")

        code, data = self._http_get("/api/state")
        self.assertEqual(code, 200)
        self.assertIsInstance(data, dict)

        code, data = self._http_get("/api/projects")
        self.assertEqual(code, 200)
        self.assertIn("projects", data)

        # 2. Settings
        code, data = self._http_get("/api/settings")
        self.assertEqual(code, 200)
        self.assertIsInstance(data, dict)

        code, data = self._http_get("/api/governance")
        self.assertEqual(code, 200)
        self.assertIsInstance(data, dict)

        code, data = self._http_get("/api/customizations/mcp")
        self.assertEqual(code, 200)
        self.assertEqual(data.get("status"), "success")

        # 3. OmniRoute
        code, data = self._http_get("/api/omniroute/config")
        self.assertEqual(code, 200)
        self.assertIn("omniroute_url", data)

        code, data = self._http_get("/api/opencode/detect")
        self.assertEqual(code, 200)
        self.assertEqual(data.get("status"), "ok")

        # 4. Models
        code, data = self._http_get("/api/local-worker/status")
        self.assertEqual(code, 200)
        self.assertEqual(data.get("status"), "ok")

        code, data = self._http_get("/api/local-worker/models")
        self.assertEqual(code, 200)
        self.assertEqual(data.get("status"), "ok")

        # 5. PTY
        code, data = self._http_get("/api/terminal/sessions")
        self.assertEqual(code, 200)
        self.assertIsInstance(data, list)

        # 6. Orchestrator
        code, data = self._http_get("/api/handoff")
        self.assertEqual(code, 200)

        code, data = self._http_get("/api/fs/tree")
        self.assertEqual(code, 200)
        self.assertIn("entries", data)

        # 7. Zeus Chat
        code, data = self._http_post(
            "/api/chat/validate-multimodal",
            {"model_id": "auto"}
        )
        self.assertEqual(code, 200)
        self.assertIn("status", data)

    def test_05_websocket_connection(self):
        """Validação funcional do canal WebSocket /ws gerenciado pelo ConnectionManager."""
        async def _test_ws():
            async with websockets.connect(self.ws_url) as ws:
                first_msg_raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                first_msg = json.loads(first_msg_raw)
                self.assertIn(first_msg.get("event"), ["PROJECTS_UPDATED", "STATE_FULL"])

                second_msg_raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                second_msg = json.loads(second_msg_raw)
                self.assertIn(second_msg.get("event"), ["PROJECTS_UPDATED", "STATE_FULL"])

        asyncio.run(_test_ws())

    def test_06_utility_exports_and_compatibility(self):
        """Garante exportação de utilitários em server/web_server.py para compatibilidade retroativa."""
        expected_symbols = [
            "is_port_in_use",
            "handle_port_conflict",
            "has_listening_socket",
            "create_bound_socket",
            "db",
            "manager",
            "pty_session_manager",
            "ollama_process_manager",
            "get_fs_tree",
            "read_fs_file",
            "get_local_worker_queue",
            "get_local_worker_hf_search",
            "get_opencode_credentials",
            "SwitchProjectPayload",
            "post_switch_project",
            "create_terminal_session",
            "get_terminal_sessions",
            "delete_terminal_session",
            "_resolve_project_fs_root",
            "get_customizations_mgr",
            "set_customizations_mgr",
        ]

        for sym in expected_symbols:
            self.assertTrue(
                hasattr(web_server, sym),
                f"server/web_server.py deve exportar '{sym}' para compatibilidade com a suíte de testes",
            )


if __name__ == "__main__":
    unittest.main()
