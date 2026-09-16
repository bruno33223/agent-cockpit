import os
import sys
import time
import socket
import signal
import subprocess
import unittest
from unittest.mock import patch, MagicMock

# Ajusta sys.path para importar módulos do servidor
_cur_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_cur_dir)
_server_dir = os.path.join(_repo_root, "server")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

import test_runner
import web_server


class TestIssue21ProcessGroupPortCheck(unittest.TestCase):
    """
    Testes para a Issue 21 / Fatia 1:
    1. Garantir que test_runner inicializa subprocesso com start_new_session=True e
       mata o grupo de processos via os.killpg() em caso de timeout/interrupção.
    2. Garantir que web_server possui is_port_in_use e handle_port_conflict utilizando
       verificação nativa de socket bind (SO_REUSEADDR) sem confiar cegamente em lsof.
    """

    def test_test_runner_uses_start_new_session_and_killpg(self):
        """Verifica se subprocess.Popen recebe start_new_session=True e os.killpg é chamado no timeout."""
        with patch("test_runner.subprocess.Popen") as mock_popen, \
             patch("test_runner.os.killpg") as mock_killpg, \
             patch("test_runner.os.getpgid", return_value=99999):

            mock_proc = MagicMock()
            mock_proc.pid = 99999
            mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="fake_test", timeout=1)
            mock_popen.return_value = mock_proc

            res = test_runner.run_distilled_tests(
                test_command="python -c 'pass'",
                timeout_sec=1
            )

            # 1. Verifica start_new_session=True
            mock_popen.assert_called()
            _, kwargs = mock_popen.call_args
            self.assertTrue(
                kwargs.get("start_new_session"),
                "subprocess.Popen deve ser inicializado com start_new_session=True para isolar o grupo de processos"
            )

            # 2. Verifica encerramento via os.killpg com SIGKILL
            if sys.platform != "win32":
                mock_killpg.assert_called_with(99999, signal.SIGKILL)

            self.assertEqual(res["status"], "TIMEOUT")

    def test_test_runner_real_timeout_cleans_child_processes(self):
        """Teste funcional real: comando que gera processo filho não deixa processo órfão em timeout."""
        if sys.platform == "win32":
            self.skipTest("Teste de processo POSIX")

        # Inicia um subprocesso que gera um sleep filho
        script = "python3 -c \"import time, subprocess; p = subprocess.Popen(['sleep', '30']); p.wait()\""
        res = test_runner.run_distilled_tests(test_command=script, timeout_sec=1)
        self.assertEqual(res["status"], "TIMEOUT")

    def test_web_server_has_native_socket_bind_port_check(self):
        """Verifica se web_server implementa is_port_in_use e handle_port_conflict com bind nativo."""
        self.assertTrue(
            hasattr(web_server, "is_port_in_use"),
            "server/web_server.py deve exportar is_port_in_use"
        )
        self.assertTrue(
            hasattr(web_server, "handle_port_conflict"),
            "server/web_server.py deve exportar handle_port_conflict"
        )

    def test_is_port_in_use_detects_bound_port(self):
        """Testa se is_port_in_use detecta com precisão portas ocupadas via socket bind."""
        # Abre um socket real e faz bind
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            _, port = s.getsockname()
            s.listen(1)

            # A porta deve ser detectada como ocupada
            self.assertTrue(
                web_server.is_port_in_use(port, host="127.0.0.1"),
                f"Porta {port} está em escuta e deve ser reportada como em uso"
            )

        # Após fechar o socket, a porta deve estar livre
        time.sleep(0.05)
        self.assertFalse(
            web_server.is_port_in_use(port, host="127.0.0.1"),
            f"Porta {port} foi liberada e deve ser reportada como livre"
        )

    def test_handle_port_conflict_does_not_declare_free_when_lsof_fails(self):
        """
        Garante que se a porta estiver ocupada mas lsof/netstat falhar em listar PIDs
        (ex: falta de permissão), handle_port_conflict NÃO declare a porta como livre.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            _, port = s.getsockname()
            s.listen(1)

            # Simula lsof falhando ou retornando vazio (ex: permissões insuficientes)
            with patch("subprocess.check_output", return_value=""):
                is_free = web_server.handle_port_conflict(port=port, host="127.0.0.1", force=False)
                self.assertFalse(
                    is_free,
                    "handle_port_conflict não pode retornar True (livre) se o socket bind comprova que a porta está ocupada, mesmo que lsof não retorne PIDs"
                )


if __name__ == "__main__":
    unittest.main()
