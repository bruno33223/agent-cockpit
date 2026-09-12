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

# Configura paths
SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from web_server import app
from state_store import db


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestLocalWorkerAPI(unittest.TestCase):
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

        # Aguarda servidor iniciar
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

    def _http_get(self, endpoint):
        req = urllib.request.Request(f"{self.base_url}{endpoint}", method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.getcode(), data

    def _http_post(self, endpoint, payload):
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{endpoint}",
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.getcode(), data

    def test_get_local_worker_status(self):
        """Verifica GET /api/local-worker/status com dados de configuração e conectividade."""
        status_code, data = self._http_get("/api/local-worker/status")
        self.assertEqual(status_code, 200)
        self.assertIn("online", data)
        self.assertIn("provider", data)
        self.assertIn("endpoint", data)
        self.assertIn("model", data)

    def test_get_local_worker_models(self):
        """Verifica GET /api/local-worker/models com lista de modelos instalados e recomendados."""
        status_code, data = self._http_get("/api/local-worker/models")
        self.assertEqual(status_code, 200)
        self.assertIn("installed", data)
        self.assertIn("recommended", data)
        self.assertIsInstance(data["installed"], list)
        self.assertIsInstance(data["recommended"], list)
        self.assertGreater(len(data["recommended"]), 0)
        # Verifica se modelos essenciais estão nas recomendações
        rec_names = [m if isinstance(m, str) else m.get("name") for m in data["recommended"]]
        self.assertTrue(any("qwen" in name.lower() for name in rec_names))

    def test_post_local_worker_select(self):
        """Verifica POST /api/local-worker/select para alternar o modelo ativo."""
        target_model = "qwen2.5-coder:1.5b"
        status_code, data = self._http_post("/api/local-worker/select", {"model": target_model})
        self.assertEqual(status_code, 200)
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("model"), target_model)

        # Confirma que status reflete a nova seleção
        _, status_data = self._http_get("/api/local-worker/status")
        self.assertEqual(status_data.get("model"), target_model)

    def test_post_local_worker_select_validation(self):
        """Verifica se payload inválido em POST /api/local-worker/select é rejeitado."""
        try:
            status_code, data = self._http_post("/api/local-worker/select", {"model": ""})
            self.assertIn(status_code, [400, 422])
        except urllib.error.HTTPError as e:
            self.assertIn(e.code, [400, 422])

    def test_post_local_worker_pull(self):
        """Verifica POST /api/local-worker/pull para iniciar download de novo modelo."""
        target_model = "deepseek-coder:6.7b"
        status_code, data = self._http_post("/api/local-worker/pull", {"model": target_model})
        self.assertEqual(status_code, 200)
        self.assertEqual(data.get("status"), "pulling")
        self.assertEqual(data.get("model"), target_model)
        self.assertIn("Acompanhe o progresso no Console de Logs", data.get("message", ""))

    def test_post_local_worker_pull_broadcast(self):
        """Verifica se thread de background chama client.pull_model e faz broadcast_sync com model_pull_complete."""
        from unittest.mock import patch, MagicMock, ANY
        with patch("web_server._get_local_worker_client") as mock_get_client, \
             patch("web_server.manager.broadcast_sync") as mock_broadcast:
            mock_client = MagicMock()
            def fake_pull(model, stream=True, progress_callback=None):
                if progress_callback:
                    progress_callback({"status": "downloading", "completed": 50, "total": 100})
                return {"status": "success"}
            mock_client.pull_model.side_effect = fake_pull
            mock_get_client.return_value = (mock_client, {})

            status_code, data = self._http_post("/api/local-worker/pull", {"model": "qwen2.5-coder:7b"})
            self.assertEqual(status_code, 200)
            self.assertEqual(data.get("status"), "pulling")

            # Aguarda a thread terminar
            time.sleep(0.2)
            mock_client.pull_model.assert_called_with("qwen2.5-coder:7b", stream=True, progress_callback=ANY)
            mock_broadcast.assert_any_call("model_pull_progress", {"model": "qwen2.5-coder:7b", "progress": {"status": "downloading", "completed": 50, "total": 100}})
            mock_broadcast.assert_any_call("model_pull_complete", {"model": "qwen2.5-coder:7b", "status": "success"})

    def test_post_local_worker_pull_validation(self):
        """Verifica se payload inválido em POST /api/local-worker/pull é rejeitado."""
        try:
            status_code, data = self._http_post("/api/local-worker/pull", {"model": ""})
            self.assertIn(status_code, [400, 422])
        except urllib.error.HTTPError as e:
            self.assertIn(e.code, [400, 422])

    def test_get_local_worker_queue(self):
        """Verifica se GET /api/local-worker/queue retorna a estrutura completa da fila."""
        status_code, data = self._http_get("/api/local-worker/queue")
        self.assertEqual(status_code, 200)
        self.assertIn("is_busy", data)
        self.assertIn("active_task", data)
        self.assertIn("queue_length", data)
        self.assertIn("queued_tasks", data)
        self.assertIn("message", data)

    def test_local_worker_queue_broadcast_on_update(self):
        """Verifica se enfileiramento e liberação disparam broadcast de worker_queue_updated."""
        from unittest.mock import patch
        from workers.worker_queue import local_worker_queue

        with patch("web_server.manager.broadcast_sync") as mock_broadcast:
            ticket = local_worker_queue.enqueue("slice-api-test", "test.html", "Instrução de teste da API")
            mock_broadcast.assert_called_with("worker_queue_updated", local_worker_queue.get_queue_status())

            # Consulta com slice_id
            status_code, data = self._http_get("/api/local-worker/queue?slice_id=slice-api-test")
            self.assertEqual(status_code, 200)
            self.assertEqual(data.get("your_position"), 1)

            # Liberação
            local_worker_queue.release_worker(ticket, status="cancelled")
            mock_broadcast.assert_called_with("worker_queue_updated", local_worker_queue.get_queue_status())

    def test_local_worker_ui_elements(self):
        """Verifica se todos os elementos visuais do Local Worker estão presentes no HTML servido."""
        req = urllib.request.Request(f"{self.base_url}/", method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            html = resp.read().decode("utf-8")
            self.assertEqual(resp.getcode(), 200)
            self.assertIn("local-worker-card", html, "Card local-worker-card ausente no HTML")
            self.assertIn("lw-status-badge", html, "Badge lw-status-badge ausente no HTML")
            self.assertIn("lw-sidebar-select", html, "Seletor lw-sidebar-select ausente no HTML")
            self.assertIn("modal-model-download", html, "Modal modal-model-download ausente no HTML")
            self.assertIn("qwen2.5-coder:7b", html, "Modelo qwen2.5-coder:7b ausente nas recomendações do modal")
            self.assertIn("deepseek-coder:6.7b", html, "Modelo deepseek-coder:6.7b ausente nas recomendações do modal")
            self.assertIn("input-custom-model", html, "Input input-custom-model ausente no formulário do modal")
            # Elementos da Fila de Tarefas da GPU
            self.assertIn("worker-queue-card", html, "Card worker-queue-card ausente no HTML")
            self.assertIn("lw-queue-status-badge", html, "Badge lw-queue-status-badge ausente no HTML")
            self.assertIn("lw-active-task-container", html, "Container lw-active-task-container ausente no HTML")
            self.assertIn("lw-queue-list-container", html, "Container lw-queue-list-container ausente no HTML")


if __name__ == "__main__":
    unittest.main()

