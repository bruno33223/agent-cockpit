import os
import sys
import time
import json
import tempfile
import shutil
import unittest
import threading
from unittest.mock import MagicMock, patch

# Ajusta sys.path para importar módulos do servidor
_cur_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_cur_dir)
_server_dir = os.path.join(_repo_root, "server")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from workers.worker_queue import LocalWorkerQueue


class TestIssue22WorkerQueue(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cockpit_issue22_test_")
        self.snapshot_file = os.path.join(self.temp_dir, "states", "worker_queue.json")
        self.queue = LocalWorkerQueue(snapshot_path=self.snapshot_file)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        try:
            from workers.worker_queue import local_worker_queue, DEFAULT_SNAPSHOT_PATH
            if local_worker_queue:
                with local_worker_queue._lock:
                    local_worker_queue._waiting_queue.clear()
                    local_worker_queue._active_task = None
                    local_worker_queue._tickets.clear()
                    local_worker_queue._history.clear()
            if os.path.exists(DEFAULT_SNAPSHOT_PATH):
                os.remove(DEFAULT_SNAPSHOT_PATH)
        except Exception:
            pass

    def test_enqueue_invokes_condition_notify_all(self):
        """Verifica se enqueue() invoca explicitamente condition.notify_all() sob o lock."""
        cond = getattr(self.queue, "condition", getattr(self.queue, "_condition", None))
        self.assertIsNotNone(cond, "A fila deve expor ou conter variável de condição")
        
        with patch.object(cond, "notify_all") as mock_notify:
            ticket_id = self.queue.enqueue("slice-1", "server/foo.py", "Test instruction")
            self.assertTrue(ticket_id.startswith("ticket-"))
            mock_notify.assert_called_once()

    def test_enqueue_wakes_consumer_thread_waiting_in_get_job(self):
        """Verifica se thread consumidora bloqueada em get_job() acorda imediatamente ao chamar enqueue()."""
        self.assertTrue(hasattr(self.queue, "get_job"), "LocalWorkerQueue deve implementar método get_job()")
        
        consumed_job = []
        started_event = threading.Event()
        elapsed_time = []

        def consumer_worker():
            started_event.set()
            t0 = time.time()
            job = self.queue.get_job(timeout=3.0)
            elapsed = time.time() - t0
            elapsed_time.append(elapsed)
            if job:
                consumed_job.append(job)

        consumer_thread = threading.Thread(target=consumer_worker, daemon=True)
        consumer_thread.start()

        # Aguarda a thread consumidora iniciar e entrar em espera
        self.assertTrue(started_event.wait(timeout=1.0))
        time.sleep(0.1)  # Garante que entrou em condition.wait

        # Enfileira nova tarefa
        t_before_enqueue = time.time()
        ticket_id = self.queue.enqueue("slice-1", "test.py", "wake up consumer")

        consumer_thread.join(timeout=1.5)
        self.assertFalse(consumer_thread.is_alive(), "A thread consumidora deveria ter acordado imediatamente")
        self.assertEqual(len(consumed_job), 1, "A thread consumidora deve ter recebido o job enfileirado")
        self.assertEqual(consumed_job[0]["ticket_id"], ticket_id)
        self.assertEqual(consumed_job[0]["slice_id"], "slice-1")
        self.assertLess(elapsed_time[0], 1.5, "O tempo de desbloqueio deve ser imediato (< 1.5s), não esperando timeout de 3.0s")

    def test_queue_persistence_snapshot_cross_process_observable(self):
        """
        Garante que a fila salva snapshots atômicos com file lock em arquivo compartilhado
        (ex: states/worker_queue.json), permitindo que outro processo (instância separada)
        leia o estado idêntico (jobs ativos, na fila e histórico).
        """
        self.assertTrue(hasattr(self.queue, "save_snapshot"), "LocalWorkerQueue deve ter save_snapshot()")
        self.assertTrue(hasattr(self.queue, "load_snapshot"), "LocalWorkerQueue deve ter load_snapshot()")

        # Simula Processo A (MCP Server): enfileira e adquire worker
        ticket1 = self.queue.enqueue("slice-1", "file1.py", "task 1")
        ticket2 = self.queue.enqueue("slice-2", "file2.py", "task 2")
        acquired = self.queue.acquire_worker(ticket1)
        self.assertTrue(acquired)

        # O snapshot deve ter sido persistido no arquivo compartilhado
        self.assertTrue(os.path.exists(self.snapshot_file), f"Snapshot deve existir em {self.snapshot_file}")

        # Simula Processo B (Web Server): nova instância lendo o mesmo snapshot
        queue_proc_b = LocalWorkerQueue(snapshot_path=self.snapshot_file)
        status_b = queue_proc_b.get_queue_status(slice_id="slice-2")

        # Verifica consistência entre processos
        self.assertTrue(status_b["is_busy"])
        self.assertIsNotNone(status_b["active_task"])
        self.assertEqual(status_b["active_task"]["ticket_id"], ticket1)
        self.assertEqual(status_b["active_task"]["slice_id"], "slice-1")
        self.assertEqual(status_b["queue_length"], 1)
        self.assertEqual(status_b["queued_tasks"][0]["ticket_id"], ticket2)
        self.assertEqual(status_b["your_position"], 1)

        # Processo A finaliza ticket 1
        self.queue.release_worker(ticket1, status="completed", tokens=150, duration=1.2)

        # Processo B relê status atualizado
        status_b2 = queue_proc_b.get_queue_status()
        self.assertFalse(status_b2["is_busy"])
        self.assertEqual(status_b2["queue_length"], 1)
        self.assertEqual(len(status_b2["history"]), 1)
        self.assertEqual(status_b2["history"][0]["ticket_id"], ticket1)
        self.assertEqual(status_b2["history"][0]["status"], "completed")

    def test_web_server_queue_endpoint_reads_shared_snapshot(self):
        """Garante que o endpoint get_local_worker_queue lê o snapshot compartilhado se disponível."""
        from server.web_server import get_local_worker_queue
        import server.workers.worker_queue as wq_module

        # Escreve um snapshot mock simulando escrita pelo mcp_server
        snapshot_data = {
            "is_busy": True,
            "active_task": {
                "ticket_id": "ticket-mcp-process",
                "slice_id": "slice-1",
                "target_file": "server/foo.py",
                "status": "running",
                "started_at": time.time(),
                "elapsed_seconds": 2.5
            },
            "queue_length": 1,
            "queued_tasks": [
                {
                    "ticket_id": "ticket-mcp-queued",
                    "slice_id": "slice-2",
                    "position": 1,
                    "target_file": "server/bar.py"
                }
            ],
            "history": []
        }

        os.makedirs(os.path.dirname(self.snapshot_file), exist_ok=True)
        with open(self.snapshot_file, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f)

        # Patch no caminho padrão do snapshot para apontar para self.snapshot_file temporário
        import workers.worker_queue as wq_mod_workers
        with patch.object(wq_module, "DEFAULT_SNAPSHOT_PATH", self.snapshot_file), \
             patch.object(wq_mod_workers, "DEFAULT_SNAPSHOT_PATH", self.snapshot_file):
            data = get_local_worker_queue(slice_id="slice-2")
            self.assertTrue(data["is_busy"])
            self.assertEqual(data["active_task"]["ticket_id"], "ticket-mcp-process")
            self.assertEqual(data["queue_length"], 1)
            self.assertEqual(data["your_position"], 1)


if __name__ == "__main__":
    unittest.main()
