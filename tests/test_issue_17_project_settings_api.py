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

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from web_server import app, db


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestProjectSettingsAPI(unittest.TestCase):
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

    def _http_request(self, endpoint, method="GET", payload=None):
        url = f"{self.base_url}{endpoint}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                status_code = resp.getcode()
                body = resp.read().decode("utf-8")
                return status_code, json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"raw": body}
            return e.code, parsed

    def test_01_get_project_settings_default_inheritance(self):
        """GET /api/projects/{project_id}/settings retorna defaults de General quando não há overrides."""
        project_id = "test-proj-alpha"
        status, data = self._http_request(f"/api/projects/{project_id}/settings", method="GET")
        self.assertEqual(status, 200)
        self.assertIn("project_id", data)
        self.assertEqual(data["project_id"], project_id)
        self.assertIn("effective_settings", data)
        self.assertIn("overrides", data)
        self.assertIn("general_defaults", data)
        self.assertEqual(data["overrides"], {})
        # Herança: effective_settings deve conter as chaves gerais
        self.assertIn("enable_local_ai", data["effective_settings"])
        self.assertIn("model", data["effective_settings"])

    def test_02_put_project_settings_overrides(self):
        """PUT /api/projects/{project_id}/settings salva overrides e retorna os novos valores efetivos."""
        project_id = "test-proj-alpha"
        payload = {
            "overrides": {
                "model": "qwen2.5-coder:7b-instruct",
                "enable_local_ai": True,
                "circuit_breaker_threshold": 5
            }
        }
        status, data = self._http_request(f"/api/projects/{project_id}/settings", method="PUT", payload=payload)
        self.assertEqual(status, 200)
        self.assertEqual(data["project_id"], project_id)
        self.assertEqual(data["effective_settings"]["model"], "qwen2.5-coder:7b-instruct")
        self.assertEqual(data["effective_settings"]["enable_local_ai"], True)
        self.assertEqual(data["effective_settings"]["circuit_breaker_threshold"], 5)
        self.assertEqual(data["overrides"]["model"], "qwen2.5-coder:7b-instruct")

    def test_03_post_project_settings_overrides_direct_keys(self):
        """POST /api/projects/{project_id}/settings também aceita chaves diretamente no payload."""
        project_id = "test-proj-beta"
        payload = {
            "model": "deepseek-coder-v2:16b",
            "delegate_styles_to_cloud": False
        }
        status, data = self._http_request(f"/api/projects/{project_id}/settings", method="POST", payload=payload)
        self.assertEqual(status, 200)
        self.assertEqual(data["project_id"], project_id)
        self.assertEqual(data["effective_settings"]["model"], "deepseek-coder-v2:16b")
        self.assertEqual(data["effective_settings"]["delegate_styles_to_cloud"], False)
        self.assertEqual(data["overrides"]["model"], "deepseek-coder-v2:16b")

    def test_04_delete_project_settings_overrides_restores_inheritance(self):
        """DELETE /api/projects/{project_id}/settings/overrides limpa overrides e restaura herança."""
        project_id = "test-proj-alpha"
        status, data = self._http_request(f"/api/projects/{project_id}/settings/overrides", method="DELETE")
        self.assertEqual(status, 200)
        self.assertEqual(data["project_id"], project_id)
        self.assertEqual(data["overrides"], {})
        # Efetivos agora são idênticos aos defaults gerais
        self.assertEqual(data["effective_settings"]["model"], data["general_defaults"]["model"])
        self.assertEqual(data["effective_settings"]["circuit_breaker_threshold"], data["general_defaults"]["circuit_breaker_threshold"])


if __name__ == "__main__":
    unittest.main()
