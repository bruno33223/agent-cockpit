import os
import sys
import json
import time
import socket
import tempfile
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
from workers.hf_cache import HFModelCache, get_default_hf_cache
from web_server import app, get_local_worker_hf_search


class TestHFHubCacheAndResilience(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_cache_file = os.path.join(self.temp_dir.name, "test_hf_cache.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("urllib.request.urlopen")
    def test_memory_cache_within_ttl_avoids_network_call(self, mock_urlopen):
        """(a) Resposta com cache em memória dentro do TTL não deve fazer nova requisição de rede."""
        mock_response_data = [
            {
                "id": "bartowski/Llama-3.2-3B-Instruct-GGUF",
                "author": "bartowski",
                "downloads": 45000,
                "likes": 850,
                "tags": ["gguf", "Q4_K_M"],
                "pipeline_tag": "text-generation"
            }
        ]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_resp.getcode.return_value = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        client = HFHubClient(timeout=3.0, ttl=3600.0, cache_file=self.temp_cache_file)

        # 1ª chamada: vai para a rede e popula o cache
        results_1 = client.search_models(query="llama", limit=5)
        self.assertEqual(len(results_1), 1)
        self.assertEqual(results_1[0]["id"], "bartowski/Llama-3.2-3B-Instruct-GGUF")
        self.assertEqual(mock_urlopen.call_count, 1)

        # 2ª chamada: deve responder do cache em memória sem invocar urlopen
        results_2 = client.search_models(query="llama", limit=5)
        self.assertEqual(len(results_2), 1)
        self.assertEqual(results_2[0]["id"], "bartowski/Llama-3.2-3B-Instruct-GGUF")
        self.assertEqual(mock_urlopen.call_count, 1, "Segunda consulta com parâmetros idênticos deve vir da memória")

    @patch("urllib.request.urlopen")
    def test_disk_cache_fallback_on_network_unreachable(self, mock_urlopen):
        """(b) Fallback para cache persistido em disco quando a rede estiver indisponível (URLError / Network unreachable)."""
        cached_models = [
            {
                "id": "unsloth/DeepSeek-R1-GGUF",
                "author": "unsloth",
                "downloads": 20000,
                "likes": 300,
                "tags": ["gguf"],
                "suggested_quants": ["Q4_K_M"],
                "ollama_tag": "hf.co/unsloth/DeepSeek-R1-GGUF"
            }
        ]
        # Pré-grava cache em disco com timestamp antigo (expirado do TTL da RAM)
        raw_disk_data = {
            "query_cache": {
                "deepseek:5:downloads:-1": {
                    "timestamp": time.time() - 7200,
                    "models": cached_models
                }
            }
        }
        with open(self.temp_cache_file, "w", encoding="utf-8") as f:
            json.dump(raw_disk_data, f)

        mock_urlopen.side_effect = urllib.error.URLError("Network unreachable")

        client = HFHubClient(timeout=3.0, ttl=3600.0, cache_file=self.temp_cache_file)
        results = client.search_models(query="deepseek", limit=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "unsloth/DeepSeek-R1-GGUF")

    @patch("urllib.request.urlopen")
    def test_aggressive_timeout_and_graceful_degradation_with_cache(self, mock_urlopen):
        """(c.1) Timeout agressivo (<= 5.0s) em requisições lentas retorna dados do cache graciosamente."""
        client = HFHubClient(cache_file=self.temp_cache_file)
        self.assertLessEqual(client.timeout, 5.0, "O timeout padrão deve ser agressivo (máximo 5.0s)")

        cached_models = [
            {
                "id": "meta/Llama-3-8B-GGUF",
                "author": "meta",
                "downloads": 1000,
                "likes": 50,
                "tags": ["gguf"],
                "suggested_quants": ["Q4_K_M"],
                "ollama_tag": "hf.co/meta/Llama-3-8B-GGUF"
            }
        ]
        raw_disk_data = {
            "query_cache": {
                "llama:5:downloads:-1": {
                    "timestamp": time.time() - 4000,
                    "models": cached_models
                }
            }
        }
        with open(self.temp_cache_file, "w", encoding="utf-8") as f:
            json.dump(raw_disk_data, f)

        mock_urlopen.side_effect = socket.timeout("Timed out connecting to Hugging Face")

        results = client.search_models(query="llama", limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "meta/Llama-3-8B-GGUF")

    @patch("urllib.request.urlopen")
    def test_aggressive_timeout_graceful_degradation_without_cache(self, mock_urlopen):
        """(c.2) Timeout agressivo sem cache retorna lista vazia graciosamente sem estourar exceção."""
        client = HFHubClient(timeout=3.0, cache_file=self.temp_cache_file)
        mock_urlopen.side_effect = socket.timeout("Timed out connecting to Hugging Face")

        results = client.search_models(query="unknown-model", limit=5)
        self.assertEqual(results, [])

    @patch("urllib.request.urlopen")
    def test_cache_ttl_expiration_triggers_network_refresh(self, mock_urlopen):
        """(d) Expiração do TTL após o tempo limite deve forçar nova consulta na rede."""
        resp_v1 = MagicMock()
        resp_v1.read.return_value = json.dumps([
            {"id": "qwen/Qwen2.5-Coder-GGUF", "downloads": 10, "tags": ["gguf"]}
        ]).encode("utf-8")
        resp_v1.getcode.return_value = 200
        resp_v1.__enter__.return_value = resp_v1

        resp_v2 = MagicMock()
        resp_v2.read.return_value = json.dumps([
            {"id": "qwen/Qwen2.5-Coder-GGUF", "downloads": 20, "tags": ["gguf"]}
        ]).encode("utf-8")
        resp_v2.getcode.return_value = 200
        resp_v2.__enter__.return_value = resp_v2

        mock_urlopen.side_effect = [resp_v1, resp_v2]

        # TTL bem curto (0.15s) para testar expiração sem delay excessivo
        client = HFHubClient(timeout=3.0, ttl=0.15, cache_file=self.temp_cache_file)

        res1 = client.search_models(query="qwen", limit=5)
        self.assertEqual(res1[0]["downloads"], 10)
        self.assertEqual(mock_urlopen.call_count, 1)

        # Espera o TTL expirar
        time.sleep(0.2)

        res2 = client.search_models(query="qwen", limit=5)
        self.assertEqual(res2[0]["downloads"], 20)
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("urllib.request.urlopen")
    def test_corrupted_disk_cache_handled_safely(self, mock_urlopen):
        """Tratamento de arquivo de cache corrompido em disco com fallback seguro."""
        with open(self.temp_cache_file, "w", encoding="utf-8") as f:
            f.write("{invalid-json-data!!")

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps([
            {"id": "test/safe-model", "downloads": 5, "tags": ["gguf"]}
        ]).encode("utf-8")
        mock_resp.getcode.return_value = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        client = HFHubClient(timeout=3.0, ttl=3600.0, cache_file=self.temp_cache_file)
        # Não deve lançar erro ao ler arquivo corrompido
        res = client.search_models(query="safe", limit=5)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "test/safe-model")

    @patch("urllib.request.urlopen")
    def test_concurrent_access_thread_safety(self, mock_urlopen):
        """Thread-safety do cache sob chamadas simultâneas de múltiplas threads."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps([
            {"id": "shared/thread-model", "downloads": 99, "tags": ["gguf"]}
        ]).encode("utf-8")
        mock_resp.getcode.return_value = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        client = HFHubClient(timeout=3.0, ttl=3600.0, cache_file=self.temp_cache_file)

        thread_errors = []

        def worker(q):
            try:
                res = client.search_models(query=q, limit=5)
                if not res or res[0]["id"] != "shared/thread-model":
                    thread_errors.append(f"Inesperado para query {q}: {res}")
            except Exception as e:
                thread_errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(f"q{i%3}",)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(thread_errors, [])

    @patch("urllib.request.urlopen")
    def test_http_error_graceful_fallback(self, mock_urlopen):
        """Em caso de HTTP 500 ou 404 da API remota, degrada para cache em disco ou [] graciosamente."""
        cached_models = [
            {
                "id": "http-error/cached-model",
                "author": "http-error",
                "downloads": 50,
                "likes": 2,
                "tags": ["gguf"],
                "suggested_quants": ["Q4_K_M"],
                "ollama_tag": "hf.co/http-error/cached-model"
            }
        ]
        raw_disk_data = {
            "query_cache": {
                "httperror:5:downloads:-1": {
                    "timestamp": time.time() - 5000,
                    "models": cached_models
                }
            }
        }
        with open(self.temp_cache_file, "w", encoding="utf-8") as f:
            json.dump(raw_disk_data, f)

        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://huggingface.co/api/models",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=None
        )

        client = HFHubClient(timeout=3.0, ttl=3600.0, cache_file=self.temp_cache_file)
        results = client.search_models(query="httperror", limit=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "http-error/cached-model")

    @patch("workers.hf_hub_client.HFHubClient.search_models")
    def test_web_server_endpoint_hf_search_integration(self, mock_search):
        """Garante que a rota /api/local-worker/hf-search integra perfeitamente com o retorno do cliente."""
        mock_search.return_value = [
            {
                "id": "test/api-model",
                "author": "test",
                "downloads": 100,
                "likes": 10,
                "tags": ["gguf"],
                "suggested_quants": ["Q4_K_M"],
                "ollama_tag": "hf.co/test/api-model"
            }
        ]

        resp = get_local_worker_hf_search(query="api-model", limit=5)
        self.assertEqual(resp["query"], "api-model")
        self.assertEqual(resp["count"], 1)
        self.assertEqual(resp["models"][0]["id"], "test/api-model")

    def test_routes_registered_on_fastapi(self):
        """Garante que as rotas /api/local-worker/hf-search, /api/models/hf e /api/huggingface/models estão registradas."""
        route_paths = [r.path for r in app.routes]
        self.assertIn("/api/local-worker/hf-search", route_paths)
        self.assertIn("/api/models/hf", route_paths)
        self.assertIn("/api/huggingface/models", route_paths)

    def test_module_reexports_clean_architecture(self):
        """Garante que server.hf_cache e server.hf_hub_client são acessíveis diretamente seguindo Clean Architecture."""
        from server.hf_cache import HFModelCache as ServerHFModelCache
        from server.hf_hub_client import HFHubClient as ServerHFHubClient, search_hf_models as server_search
        self.assertIsNotNone(ServerHFModelCache)
        self.assertIsNotNone(ServerHFHubClient)
        self.assertTrue(callable(server_search))


if __name__ == "__main__":
    unittest.main()
