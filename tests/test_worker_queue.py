import os
import sys
import time
import threading
import unittest
from typing import List

# Garante path para o server
SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from workers.worker_queue import LocalWorkerQueue, local_worker_queue


import tempfile

class TestLocalWorkerQueue(unittest.TestCase):
    def setUp(self):
        # Instância isolada para cada caso de teste com arquivo de snapshot temporário
        self.temp_dir = tempfile.TemporaryDirectory()
        self.snapshot_path = os.path.join(self.temp_dir.name, "worker_queue.json")
        self.queue = LocalWorkerQueue(snapshot_path=self.snapshot_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initial_state(self):
        """Verifica se a fila inicia vazia e com a GPU livre."""
        status = self.queue.get_queue_status()
        self.assertFalse(status["is_busy"])
        self.assertIsNone(status["active_task"])
        self.assertEqual(status["queue_length"], 0)
        self.assertEqual(status["queued_tasks"], [])
        self.assertIn("livre", status["message"].lower())

    def test_enqueue_and_get_status(self):
        """Verifica enfileiramento de tarefas e cálculo de posições."""
        t1 = self.queue.enqueue("slice-1", "index.html", "Crie o cabeçalho")
        t2 = self.queue.enqueue("slice-2", "styles.css", "Crie o estilo dark")
        
        self.assertIsNotNone(t1)
        self.assertIsNotNone(t2)
        self.assertNotEqual(t1, t2)

        q_status = self.queue.get_queue_status()
        self.assertEqual(q_status["queue_length"], 2)
        self.assertFalse(q_status["is_busy"])

        # Posição individual
        t1_status = self.queue.get_ticket_status(t1)
        self.assertIsNotNone(t1_status)
        self.assertEqual(t1_status["position"], 1)
        self.assertEqual(t1_status["slice_id"], "slice-1")
        self.assertEqual(t1_status["status"], "queued")

        t2_status = self.queue.get_ticket_status(t2)
        self.assertEqual(t2_status["position"], 2)
        self.assertEqual(t2_status["slice_id"], "slice-2")

        # get_queue_status filtrado por slice_id ou ticket_id
        filtered = self.queue.get_queue_status(slice_id="slice-2")
        self.assertEqual(filtered["your_position"], 2)
        self.assertIn("2", filtered["message"])

    def test_acquire_and_release_lifecycle(self):
        """Verifica ciclo de vida de aquisição e liberação pelo worker."""
        ticket_id = self.queue.enqueue("slice-1", "main.py", "Implementar cálculo")
        
        # Adquire o worker
        acquired = self.queue.acquire_worker(ticket_id, timeout=1.0)
        self.assertTrue(acquired)

        status_busy = self.queue.get_queue_status()
        self.assertTrue(status_busy["is_busy"])
        self.assertIsNotNone(status_busy["active_task"])
        self.assertEqual(status_busy["active_task"]["ticket_id"], ticket_id)
        self.assertEqual(status_busy["queue_length"], 0)

        # Libera o worker
        self.queue.release_worker(ticket_id, status="completed", tokens=120, duration=0.45)
        
        status_idle = self.queue.get_queue_status()
        self.assertFalse(status_idle["is_busy"])
        self.assertIsNone(status_idle["active_task"])
        self.assertEqual(len(status_idle["history"]), 1)
        self.assertEqual(status_idle["history"][0]["tokens"], 120)

    def test_concurrent_fifo_execution_three_threads(self):
        """
        Garante que 3 threads simultâneas sejam processadas estritamente em ordem FIFO
        (Thread 1 -> Thread 2 -> Thread 3) e que nunca haja mais de um worker ativo ao mesmo tempo.
        """
        execution_order: List[str] = []
        max_concurrent_workers = 0
        current_concurrent_workers = 0
        counter_lock = threading.Lock()

        # Enfileira as 3 fatias
        ticket_1 = self.queue.enqueue("slice-1", "page.html", "Instrução 1")
        ticket_2 = self.queue.enqueue("slice-2", "style.css", "Instrução 2")
        ticket_3 = self.queue.enqueue("slice-3", "script.js", "Instrução 3")

        def worker_simulation(ticket_id: str, slice_id: str):
            nonlocal max_concurrent_workers, current_concurrent_workers
            acquired = self.queue.acquire_worker(ticket_id, timeout=5.0)
            if not acquired:
                return

            with counter_lock:
                current_concurrent_workers += 1
                if current_concurrent_workers > max_concurrent_workers:
                    max_concurrent_workers = current_concurrent_workers
                execution_order.append(slice_id)

            # Simula trabalho na GPU
            time.sleep(0.05)

            with counter_lock:
                current_concurrent_workers -= 1

            self.queue.release_worker(ticket_id, status="completed", tokens=50, duration=0.05)

        threads = [
            threading.Thread(target=worker_simulation, args=(ticket_1, "slice-1")),
            threading.Thread(target=worker_simulation, args=(ticket_2, "slice-2")),
            threading.Thread(target=worker_simulation, args=(ticket_3, "slice-3")),
        ]

        # Inicia as 3 threads simultaneamente
        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=6.0)

        # Validação estrita:
        # 1. Ordem de execução deve ser exatamente slice-1, slice-2, slice-3 (FIFO)
        self.assertEqual(execution_order, ["slice-1", "slice-2", "slice-3"])
        # 2. Em nenhum momento houve 2 ou mais workers executando juntos
        self.assertEqual(max_concurrent_workers, 1)
        # 3. Fila finalizada e limpa
        final_status = self.queue.get_queue_status()
        self.assertFalse(final_status["is_busy"])
        self.assertEqual(final_status["queue_length"], 0)
        self.assertEqual(len(final_status["history"]), 3)

    def test_timeout_handling(self):
        """Verifica que acquire_worker respeita timeout e remove da fila quando bloqueado."""
        t1 = self.queue.enqueue("slice-1", "a.py", "Tarefa longa")
        t2 = self.queue.enqueue("slice-2", "b.py", "Tarefa aguardando")

        # T1 adquire e não solta
        acquired_1 = self.queue.acquire_worker(t1, timeout=1.0)
        self.assertTrue(acquired_1)

        # T2 tenta adquirir com timeout curto de 0.1s
        start_t = time.time()
        acquired_2 = self.queue.acquire_worker(t2, timeout=0.1)
        duration = time.time() - start_t

        self.assertFalse(acquired_2)
        self.assertGreaterEqual(duration, 0.08)
        
        # T2 deve ter saído da fila de espera
        q_status = self.queue.get_queue_status()
        self.assertEqual(q_status["queue_length"], 0)
        
        t2_status = self.queue.get_ticket_status(t2)
        self.assertEqual(t2_status["status"], "timeout")

        # Limpeza para T1
        self.queue.release_worker(t1)

    def test_listener_callback(self):
        """Verifica se listeners registrados recebem notificações de atualização."""
        events = []

        def on_queue_change(status):
            events.append(status)

        self.queue.register_listener(on_queue_change)
        t = self.queue.enqueue("slice-1", "a.py", "Teste listener")
        self.assertGreater(len(events), 0)

        self.queue.acquire_worker(t, timeout=1.0)
        self.assertGreater(len(events), 1)

        self.queue.release_worker(t)
        self.assertGreater(len(events), 2)


if __name__ == "__main__":
    unittest.main()
