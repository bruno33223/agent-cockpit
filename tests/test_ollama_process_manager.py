"""
Testes unitários para OllamaProcessManager (Fatia 1).
Cobre: is_installed, is_port_open, start, stop, get_status, get_logs e callbacks de broadcast.
"""

import os
import sys
import time
import socket
import unittest
import subprocess
from collections import deque
from unittest.mock import patch, MagicMock, call

# Garante acesso ao pacote server
SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from workers.ollama_process_manager import OllamaProcessManager


class TestOllamaProcessManager(unittest.TestCase):
    def setUp(self):
        self.manager = OllamaProcessManager(port=11434)

    def tearDown(self):
        if self.manager.process is not None:
            try:
                self.manager.stop(timeout=0.5)
            except Exception:
                pass

    # 1. is_installed()
    @patch("shutil.which")
    def test_is_installed_found_in_path(self, mock_which):
        mock_which.return_value = "/usr/bin/ollama"
        self.assertTrue(self.manager.is_installed())
        self.assertEqual(self.manager.get_binary_path(), "/usr/bin/ollama")

    @patch("shutil.which")
    @patch("os.path.exists")
    def test_is_installed_found_in_local_bin_fallback(self, mock_exists, mock_which):
        mock_which.return_value = None
        # /usr/local/bin/ollama existe
        def side_effect(p):
            return p == "/usr/local/bin/ollama"
        mock_exists.side_effect = side_effect

        self.assertTrue(self.manager.is_installed())
        self.assertEqual(self.manager.get_binary_path(), "/usr/local/bin/ollama")

    @patch("shutil.which")
    @patch("os.path.exists")
    def test_is_installed_not_found(self, mock_exists, mock_which):
        mock_which.return_value = None
        mock_exists.return_value = False
        self.assertFalse(self.manager.is_installed())
        self.assertIsNone(self.manager.get_binary_path())

    # 2. is_port_open()
    @patch("socket.socket")
    def test_is_port_open_true(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        mock_socket_cls.return_value.__enter__.return_value = mock_sock

        self.assertTrue(self.manager.is_port_open(port=11434))
        mock_sock.connect_ex.assert_called_with(("127.0.0.1", 11434))

    @patch("socket.socket")
    def test_is_port_open_false(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 111  # Connection refused
        mock_socket_cls.return_value.__enter__.return_value = mock_sock

        self.assertFalse(self.manager.is_port_open(port=11434))

    # 3. start()
    @patch.object(OllamaProcessManager, "is_port_open")
    @patch("subprocess.Popen")
    def test_start_skips_when_already_running_on_port(self, mock_popen, mock_is_port_open):
        mock_is_port_open.return_value = True

        result = self.manager.start()

        self.assertEqual(result.get("status"), "already_running")
        self.assertTrue(result.get("running"))
        mock_popen.assert_not_called()
        self.assertIsNone(self.manager.process)

    @patch.object(OllamaProcessManager, "is_port_open")
    @patch.object(OllamaProcessManager, "get_binary_path")
    @patch("subprocess.Popen")
    def test_start_spawns_process_when_port_closed(self, mock_popen, mock_get_bin, mock_is_port_open):
        mock_is_port_open.return_value = False
        mock_get_bin.return_value = "/usr/local/bin/ollama"

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345
        mock_proc.stdout = iter(["listening on 127.0.0.1:11434\n", "model loaded\n"])
        mock_popen.return_value = mock_proc

        result = self.manager.start()

        self.assertEqual(result.get("status"), "started")
        self.assertEqual(result.get("pid"), 12345)
        mock_popen.assert_called_once_with(
            ["/usr/local/bin/ollama", "serve"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        self.assertIsNotNone(self.manager.process)

    @patch.object(OllamaProcessManager, "is_port_open")
    @patch("subprocess.Popen")
    def test_start_does_not_duplicate_if_already_spawned(self, mock_popen, mock_is_port_open):
        mock_is_port_open.return_value = False
        self.manager.process = MagicMock()
        self.manager.process.poll.return_value = None  # Process is alive
        self.manager.process.pid = 999

        result = self.manager.start()

        self.assertEqual(result.get("status"), "already_running")
        mock_popen.assert_not_called()

    # 4. stop() com SIGTERM e fallback SIGKILL
    def test_stop_graceful_sigterm(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0
        self.manager.process = mock_proc

        res = self.manager.stop(timeout=1.0)

        self.assertEqual(res.get("status"), "stopped")
        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=1.0)
        mock_proc.kill.assert_not_called()
        self.assertIsNone(self.manager.process)

    def test_stop_fallback_sigkill_on_timeout(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="ollama", timeout=1.0), 0]
        self.manager.process = mock_proc

        res = self.manager.stop(timeout=1.0)

        self.assertEqual(res.get("status"), "killed")
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        self.assertIsNone(self.manager.process)

    def test_stop_when_no_process(self):
        self.manager.process = None
        res = self.manager.stop()
        self.assertEqual(res.get("status"), "not_running")

    # 5. Buffer circular deque(maxlen=500), get_logs() e get_status()
    def test_log_buffer_maxlen_and_get_logs(self):
        self.assertEqual(self.manager.logs.maxlen, 500)

        # Inserção de mais de 500 linhas
        for i in range(600):
            self.manager._append_log(f"log line {i}")

        self.assertEqual(len(self.manager.logs), 500)
        # Últimas 100 linhas
        logs_100 = self.manager.get_logs(limit=100)
        self.assertEqual(len(logs_100), 100)
        self.assertEqual(logs_100[-1], "log line 599")
        self.assertEqual(logs_100[0], "log line 500")

    @patch.object(OllamaProcessManager, "is_installed")
    @patch.object(OllamaProcessManager, "is_port_open")
    def test_get_status(self, mock_is_port_open, mock_is_installed):
        mock_is_installed.return_value = True
        mock_is_port_open.return_value = True

        status = self.manager.get_status()
        self.assertTrue(status.get("installed"))
        self.assertTrue(status.get("port_open"))
        self.assertTrue(status.get("running"))
        self.assertEqual(status.get("port"), 11434)
        self.assertFalse(status.get("managed"))

        # Quando gerenciado
        self.manager.process = MagicMock()
        self.manager.process.poll.return_value = None
        self.manager.process.pid = 4321
        status_managed = self.manager.get_status()
        self.assertTrue(status_managed.get("managed"))
        self.assertEqual(status_managed.get("pid"), 4321)

    # 6. Callbacks de logs para WebSocket
    def test_log_callbacks_invocation(self):
        received_1 = []
        received_2 = []

        def cb1(line: str):
            received_1.append(line)

        def cb2(line: str):
            received_2.append(line)

        def cb_err(line: str):
            raise RuntimeError("Broadcast error")

        self.manager.add_log_callback(cb1)
        self.manager.add_log_callback(cb2)
        self.manager.add_log_callback(cb_err)

        self.manager._append_log("mensagem de teste 1")
        self.manager._append_log("mensagem de teste 2")

        self.assertEqual(received_1, ["mensagem de teste 1", "mensagem de teste 2"])
        self.assertEqual(received_2, ["mensagem de teste 1", "mensagem de teste 2"])

        # Teste de remoção
        self.manager.remove_log_callback(cb1)
        self.manager._append_log("mensagem de teste 3")
        self.assertEqual(len(received_1), 2)
        self.assertEqual(len(received_2), 3)


if __name__ == "__main__":
    unittest.main()
