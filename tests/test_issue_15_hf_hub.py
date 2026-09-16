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

# Configura path para importar server
SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from workers.hf_hub_client import HFHubClient, search_hf_models
from web_server import app


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestHFHubClientUnit(unittest.TestCase):
    def setUp(self):
        self.client = HFHubClient(timeout=2.0)

    @patch("urllib.request.urlopen")
    def test_search_models_parses_response_correctly(self, mock_urlopen):
        mock_response_data = [
            {
                "id": "bartowski/Llama-3.2-3B-Instruct-GGUF",
                "author": "bartowski",
                "downloads": 45000,
                "likes": 850,
                "tags": ["gguf", "llama", "Q4_K_M", "Q8_0", "conversational"],
                "pipeline_tag": "text-generation"
            },
            {
                "id": "unsloth/DeepSeek-R1-Distill-Qwen-8B-GGUF",
                "downloads": 23000,
                "likes": 410,
                "tags": ["gguf", "qwen2", "text-generation"],
                "pipeline_tag": "text-generation"
            }
        ]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_resp.getcode.return_value = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        results = self.client.search_models(query="llama", limit=5)

        self.assertEqual(len(results), 2)
        
        # Validação do primeiro modelo
        item1 = results[0]
        self.assertEqual(item1["id"], "bartowski/Llama-3.2-3B-Instruct-GGUF")
        self.assertEqual(item1["author"], "bartowski")
        self.assertEqual(item1["downloads"], 45000)
        self.assertEqual(item1["likes"], 850)
        self.assertIn("Q4_K_M", item1["suggested_quants"])
        self.assertIn("Q8_0", item1["suggested_quants"])
        self.assertEqual(item1["ollama_tag"], "hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF")

        # Validação do segundo modelo (extrai autor de id se faltar e dá fallback de quants)
        item2 = results[1]
        self.assertEqual(item2["id"], "unsloth/DeepSeek-R1-Distill-Qwen-8B-GGUF")
        self.assertEqual(item2["author"], "unsloth")
        self.assertEqual(item2["downloads"], 23000)
        self.assertEqual(item2["likes"], 410)
        self.assertIn("Q4_K_M", item2["suggested_quants"])
        self.assertEqual(item2["ollama_tag"], "hf.co/unsloth/DeepSeek-R1-Distill-Qwen-8B-GGUF")

    @patch("urllib.request.urlopen")
    def test_search_models_constructs_gguf_filter_query(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"[]"
        mock_resp.getcode.return_value = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        self.client.search_models(query="qwen coder", limit=10)

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        called_url = req.full_url if hasattr(req, "full_url") else str(req)
        self.assertIn("filter=gguf", called_url)
        self.assertIn("limit=10", called_url)
        self.assertIn("search=qwen", called_url)

    @patch("urllib.request.urlopen")
    def test_search_models_handles_timeout_gracefully(self, mock_urlopen):
        mock_urlopen.side_effect = socket.timeout("Timed out connecting to Hugging Face")
        results = self.client.search_models(query="timeout-test")
        self.assertEqual(results, [])

    @patch("urllib.request.urlopen")
    def test_search_models_handles_url_error_gracefully(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Network unreachable")
        results = search_hf_models(query="network-error-test")
        self.assertEqual(results, [])


class TestHFHubServerEndpoint(unittest.TestCase):
    server_thread = None
    server = None
    port = None
    base_url = None

    @classmethod
    def setUpClass(cls):
        import uvicorn
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

    @patch("workers.hf_hub_client.HFHubClient.search_models")
    def test_get_local_worker_hf_search_endpoint(self, mock_search):
        mock_search.return_value = [
            {
                "id": "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF",
                "author": "TheBloke",
                "downloads": 9999,
                "likes": 50,
                "tags": ["gguf"],
                "suggested_quants": ["Q4_K_M", "Q8_0"],
                "ollama_tag": "hf.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF"
            }
        ]

        url = f"{self.base_url}/api/local-worker/hf-search?query=tinyllama&limit=3"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            status_code = resp.getcode()
            body = json.loads(resp.read().decode("utf-8"))

        self.assertEqual(status_code, 200)
        self.assertIn("models", body)
        self.assertEqual(len(body["models"]), 1)
        self.assertEqual(body["models"][0]["id"], "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF")
        self.assertEqual(body["models"][0]["ollama_tag"], "hf.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF")
        mock_search.assert_called_with(query="tinyllama", limit=3)


if __name__ == "__main__":
    unittest.main()
