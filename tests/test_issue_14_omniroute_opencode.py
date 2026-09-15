import os
import sys
import json
import time
import socket
import threading
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import urllib.request
import urllib.error
import uvicorn

# Configura caminhos para importar os módulos do servidor
SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import opencode_manager
from web_server import app


_real_urlopen = urllib.request.urlopen


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestOmniRouteOpenCodeIntegration(unittest.TestCase):
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
                with _real_urlopen(f"{cls.base_url}/api/health", timeout=1.0) as resp:
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
        with _real_urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.getcode(), data


    def test_auto_detect_credentials_from_env(self):
        """Verifica se detect_opencode_credentials recupera valores das variáveis de ambiente."""
        env_vars = {
            "OMNIROUTE_URL": "http://env-omniroute:20128/v1",
            "OMNIROUTE_API_KEY": "sk-env-test-key",
            "OPENCODE_MODEL": "env-model"
        }
        with patch.dict(os.environ, env_vars, clear=False):
            detected = opencode_manager.detect_opencode_credentials()
            self.assertIsInstance(detected, dict)
            self.assertEqual(detected.get("omniroute_url"), "http://env-omniroute:20128/v1")
            self.assertEqual(detected.get("api_key"), "sk-env-test-key")
            self.assertEqual(detected.get("model"), "env-model")
            self.assertIn("env", detected.get("sources", []))

    def test_auto_detect_credentials_from_config_file(self):
        """Verifica se detect_opencode_credentials lê ~/.config/opencode/opencode.json ou config.json."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "opencode.json")
            sample_cfg = {
                "provider": {
                    "omniroute": {
                        "options": {
                            "baseURL": "http://config-file-omniroute:9999/v1",
                            "apiKey": "sk-from-file"
                        },
                        "models": {
                            "custom-model": {"name": "Custom Model"}
                        }
                    }
                },
                "model": "omniroute/custom-model"
            }
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(sample_cfg, f)

            with patch("os.path.expanduser") as mock_expanduser, patch.dict(os.environ, {}, clear=True):
                mock_expanduser.side_effect = lambda p: tmp_dir if p == "~/.config/opencode" or "~/.config/opencode" in p else os.path.expanduser(p)
                detected = opencode_manager.detect_opencode_credentials(config_dir=tmp_dir)
                self.assertIsInstance(detected, dict)
                self.assertEqual(detected.get("omniroute_url"), "http://config-file-omniroute:9999/v1")
                self.assertEqual(detected.get("api_key"), "sk-from-file")
                self.assertEqual(detected.get("model"), "custom-model")
                self.assertIn("file", detected.get("sources", []))

    def test_detect_omniroute_connectors_from_models(self):
        """Verifica se detect_omniroute_connectors agrupa modelos por provedor/conector."""
        fake_models_resp = {
            "data": [
                {"id": "openai/gpt-4o"},
                {"id": "openai/gpt-4o-mini"},
                {"id": "anthropic/claude-3-5-sonnet"},
                {"id": "ollama/deepseek-r1"},
                {"id": "standalone-model"}
            ]
        }
        
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(fake_models_resp).encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        with patch("opencode_manager.urllib.request.urlopen", return_value=mock_response):
            connectors = opencode_manager.detect_omniroute_connectors("http://localhost:20128/v1")
            self.assertIsInstance(connectors, list)
            connector_ids = [c["id"] for c in connectors]
            self.assertIn("openai", connector_ids)
            self.assertIn("anthropic", connector_ids)
            self.assertIn("ollama", connector_ids)
            self.assertIn("general", connector_ids)

            openai_conn = next(c for c in connectors if c["id"] == "openai")
            self.assertIn("openai/gpt-4o", openai_conn["models"])
            self.assertEqual(openai_conn["count"], 2)

    def test_check_omniroute_health_includes_connectors_and_autodetect(self):
        """Verifica se check_omniroute_health agrega conectores detectados na resposta."""
        fake_models_resp = {
            "data": [
                {"id": "openai/gpt-4o"},
                {"id": "groq/llama-3.3-70b"}
            ]
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(fake_models_resp).encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        with patch("opencode_manager.urllib.request.urlopen", return_value=mock_response):
            health = opencode_manager.check_omniroute_health("http://localhost:20128/v1")
            self.assertTrue(health.get("online"))
            self.assertIn("connectors", health)
            self.assertEqual(len(health["connectors"]), 2)
            self.assertIn("auto_detected", health)

    def test_api_omniroute_connectors_endpoint(self):
        """Valida se o endpoint GET /api/omniroute/connectors responde com a lista de conectores."""
        fake_models_resp = {
            "data": [
                {"id": "anthropic/claude-3-opus"},
                {"id": "google/gemini-2.0-flash"}
            ]
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(fake_models_resp).encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        with patch("opencode_manager.urllib.request.urlopen", return_value=mock_response):
            code, data = self._http_get("/api/omniroute/connectors")
            self.assertEqual(code, 200)
            self.assertTrue(data.get("online"))
            self.assertIn("connectors", data)
            connector_ids = [c["id"] for c in data["connectors"]]
            self.assertIn("anthropic", connector_ids)
            self.assertIn("google", connector_ids)

    def test_api_omniroute_status_endpoint_enriched(self):
        """Valida se GET /api/omniroute/status retorna connectors e informações enriquecidas."""
        fake_models_resp = {
            "data": [
                {"id": "openai/gpt-4.5-preview"}
            ]
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(fake_models_resp).encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        with patch("opencode_manager.urllib.request.urlopen", return_value=mock_response):
            code, data = self._http_get("/api/omniroute/status")
            self.assertEqual(code, 200)
            self.assertTrue(data.get("online"))
            self.assertIn("connectors", data)
            self.assertIn("auto_detected", data)


if __name__ == "__main__":
    unittest.main()
