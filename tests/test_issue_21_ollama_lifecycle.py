"""
Testes unitários para ciclo de vida e concorrência do OllamaProcessManager (Issue #21).
Valida:
1. start() e stop() são protegidos por threading.Lock mútuo evitando instâncias duplicadas concorrentes.
2. start() realiza polling ativo na porta TCP (wait_for_port) antes de retornar sucesso e trata timeout/falha.
"""

import os
import sys
import time
import socket
import threading
import unittest
from unittest.mock import patch, MagicMock

# Garante acesso ao pacote server
SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from workers.ollama_process_manager import OllamaProcessManager


class TestIssue21OllamaLifecycle(unittest.TestCase):
    def setUp(self):
        self.manager = OllamaProcessManager(host="127.0.0.1", port=11434)

    def tearDown(self):
        if self.manager.process is not None:
            try:
                self.manager.stop(timeout=0.2)
            except Exception:
                pass

    @patch("subprocess.Popen")
    @patch.object(OllamaProcessManager, "get_binary_path")
    def test_start_active_tcp_polling_success(self, mock_get_bin, mock_popen):
        """
        start() deve realizar polling ativo na porta TCP até que ela abra, antes de retornar sucesso.
        """
        mock_get_bin.return_value = "/usr/bin/ollama"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 9999
        mock_proc.stdout = iter([])
        mock_popen.return_value = mock_proc

        # Simula is_port_open retornando False no check inicial, False na 1ª tentativa de polling, True na 2ª
        with patch.object(self.manager, "is_port_open", side_effect=[False, False, True]) as mock_port:
            res = self.manager.start(startup_timeout=2.0)
            self.assertEqual(res["status"], "started")
            self.assertTrue(res["running"])
            self.assertEqual(res["pid"], 9999)
            # Verificou porta mais de uma vez (check inicial + polling)
            self.assertGreaterEqual(mock_port.call_count, 2)

    @patch("subprocess.Popen")
    @patch.object(OllamaProcessManager, "get_binary_path")
    def test_start_active_tcp_polling_timeout(self, mock_get_bin, mock_popen):
        """
        start() deve encerrar o processo e lançar TimeoutError / RuntimeError se o polling da porta falhar.
        """
        mock_get_bin.return_value = "/usr/bin/ollama"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 8888
        mock_proc.stdout = iter([])
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        # Porta nunca abre
        with patch.object(self.manager, "is_port_open", return_value=False):
            with self.assertRaises((TimeoutError, RuntimeError)):
                self.manager.start(startup_timeout=0.2)

            # Garante que o processo foi limpo/terminado após o timeout
            mock_proc.terminate.assert_called()

    @patch("subprocess.Popen")
    @patch.object(OllamaProcessManager, "get_binary_path")
    def test_start_and_stop_mutual_lock_concurrency(self, mock_get_bin, mock_popen):
        """
        start() e stop() devem compartilhar um threading.Lock mútuo no controle de ciclo de vida.
        """
        mock_get_bin.return_value = "/usr/bin/ollama"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 7777
        mock_proc.stdout = iter([])
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        # Verifica existência de lock explícito de ciclo de vida
        self.assertTrue(hasattr(self.manager, "_lifecycle_lock"))
        self.assertIsInstance(self.manager._lifecycle_lock, type(threading.Lock()))

        # Testa concorrência real entre duas threads chamando start simultaneamente
        started_count = [0]
        already_running_count = [0]

        def worker_start():
            with patch.object(self.manager, "is_port_open", side_effect=[False, True, True, True]):
                r = self.manager.start(startup_timeout=1.0)
                if r.get("status") == "started":
                    started_count[0] += 1
                elif r.get("status") == "already_running":
                    already_running_count[0] += 1

        t1 = threading.Thread(target=worker_start)
        t2 = threading.Thread(target=worker_start)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Apenas 1 thread deve ter iniciado o processo Popen
        self.assertEqual(mock_popen.call_count, 1)
        self.assertEqual(started_count[0], 1)
        self.assertEqual(already_running_count[0], 1)


if __name__ == "__main__":
    unittest.main()
