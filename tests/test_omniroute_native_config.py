import os
import sys
import json
import time
import socket
import threading
import unittest
from unittest.mock import patch, MagicMock
import urllib.request
import urllib.error
import uvicorn

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import opencode_manager
from web_server import app


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestOmniRouteNativeConfig(unittest.TestCase):
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

    # 1. Daemon Status & Control
    def test_daemon_status_endpoint(self):
        with urllib.request.urlopen(f"{self.base_url}/api/omniroute/daemon/status", timeout=3.0) as resp:
            self.assertEqual(resp.getcode(), 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("installed", data)
            self.assertIn("running", data)
            self.assertIn("url", data)

    @patch("opencode_manager.start_omniroute_daemon")
    def test_daemon_start_endpoint(self, mock_start):
        mock_start.return_value = {"status": "ok", "message": "OmniRoute iniciado com sucesso."}
        req = urllib.request.Request(
            f"{self.base_url}/api/omniroute/daemon/start",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.getcode(), 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "ok")

    # 2. Accounts CRUD
    @patch("opencode_manager.list_omniroute_accounts")
    def test_get_accounts_endpoint(self, mock_list):
        mock_list.return_value = [
            {
                "id": "conn-openai-1",
                "provider": "openai",
                "name": "OpenAI Main",
                "authType": "apikey",
                "isActive": True,
                "testStatus": "success",
                "defaultModel": "gpt-4o"
            }
        ]
        with urllib.request.urlopen(f"{self.base_url}/api/omniroute/accounts", timeout=3.0) as resp:
            self.assertEqual(resp.getcode(), 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(len(data.get("accounts", [])), 1)
            self.assertEqual(data["accounts"][0]["name"], "OpenAI Main")

    @patch("opencode_manager.add_omniroute_account")
    def test_post_account_endpoint(self, mock_add):
        mock_add.return_value = {
            "status": "ok",
            "account": {
                "id": "conn-anthropic-1",
                "provider": "anthropic",
                "name": "Anthropic Work",
                "defaultModel": "claude-3-5-sonnet-20241022"
            }
        }
        payload = {
            "provider": "anthropic",
            "name": "Anthropic Work",
            "api_key": "sk-ant-test-12345",
            "default_model": "claude-3-5-sonnet-20241022"
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/omniroute/accounts",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.getcode(), 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["account"]["provider"], "anthropic")

    @patch("opencode_manager.delete_omniroute_account")
    def test_delete_account_endpoint(self, mock_del):
        mock_del.return_value = {"status": "ok", "message": "Conta removida com sucesso."}
        req = urllib.request.Request(
            f"{self.base_url}/api/omniroute/accounts/conn-openai-1",
            method="DELETE"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.getcode(), 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "ok")

    @patch("opencode_manager.test_omniroute_account")
    def test_test_account_endpoint(self, mock_test):
        mock_test.return_value = {"valid": True, "status": "success", "message": "Conexão OK"}
        req = urllib.request.Request(
            f"{self.base_url}/api/omniroute/accounts/conn-openai-1/test",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.getcode(), 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("valid"))

    # 3. Live Models List
    @patch("opencode_manager.list_omniroute_live_models")
    def test_live_models_endpoint(self, mock_models):
        mock_models.return_value = {
            "status": "ok",
            "models": ["openai/gpt-4o", "anthropic/claude-3-5-sonnet"],
            "connectors": [
                {"id": "openai", "name": "OpenAI", "models": ["openai/gpt-4o"], "count": 1},
                {"id": "anthropic", "name": "Anthropic", "models": ["anthropic/claude-3-5-sonnet"], "count": 1}
            ],
            "active_model": "openai/gpt-4o"
        }
        with urllib.request.urlopen(f"{self.base_url}/api/omniroute/models", timeout=3.0) as resp:
            self.assertEqual(resp.getcode(), 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "ok")
            self.assertEqual(len(data["models"]), 2)
            self.assertEqual(data["active_model"], "openai/gpt-4o")


if __name__ == "__main__":
    unittest.main()
