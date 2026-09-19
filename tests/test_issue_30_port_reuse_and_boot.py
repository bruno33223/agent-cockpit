import os
import sys
import time
import socket
import unittest
from unittest.mock import patch, MagicMock

# Ajusta sys.path para importar módulos da raiz e do servidor
_cur_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_cur_dir)
_server_dir = os.path.join(_repo_root, "server")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

import run_cockpit
import web_server


class TestIssue30PortReuseAndBoot(unittest.TestCase):
    """
    Testes para a Issue #30:
    1. Verificação de que sockets em TIME_WAIT não causam falso positivo de bloqueio em handle_port_conflict.
    2. Inicialização do socket em run_cockpit.py com SO_REUSEADDR e SO_REUSEPORT (quando suportado).
    3. Diferenciação correta: se um processo real NÃO-cockpit estiver ouvindo (LISTEN), handle_port_conflict
       deve bloquear; se a porta tiver apenas socket em TIME_WAIT ou for liberável, deve permitir o boot.
    4. Inicialização limpa do Uvicorn com sockets reutilizáveis pré-vinculados.
    """

    def test_time_wait_socket_does_not_block_handle_port_conflict(self):
        """Sockets em TIME_WAIT não devem causar falso positivo de conflito de porta."""
        # Cria servidor efêmero e cliente para gerar estado TIME_WAIT real
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        srv.bind(("127.0.0.1", 0))
        _, port = srv.getsockname()
        srv.listen(1)

        cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cli.connect(("127.0.0.1", port))
        conn, _ = srv.accept()

        # Servidor fecha a conexão ativamente primeiro -> estado entra em TIME_WAIT no kernel
        conn.close()
        srv.close()
        cli.close()
        time.sleep(0.05)

        # Tanto web_server quanto run_cockpit não devem bloquear por falso positivo
        self.assertTrue(
            web_server.handle_port_conflict(port=port, host="127.0.0.1", force=False),
            "web_server.handle_port_conflict não deve bloquear em estado transitório de TIME_WAIT"
        )
        self.assertTrue(
            run_cockpit.handle_port_conflict(port=port, host="127.0.0.1", force=False),
            "run_cockpit.handle_port_conflict não deve bloquear em estado transitório de TIME_WAIT"
        )

    def test_socket_initialization_with_so_reuseaddr_and_so_reuseport(self):
        """create_bound_socket deve configurar SO_REUSEADDR e SO_REUSEPORT (se suportado) e fazer bind."""
        self.assertTrue(
            hasattr(run_cockpit, "create_bound_socket"),
            "run_cockpit deve exportar a função create_bound_socket"
        )
        sock = run_cockpit.create_bound_socket(host="127.0.0.1", port=0)
        try:
            self.assertIsInstance(sock, socket.socket)
            reuse_addr = sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)
            self.assertNotEqual(reuse_addr, 0, "SO_REUSEADDR deve estar habilitado no socket")

            if hasattr(socket, "SO_REUSEPORT"):
                reuse_port = sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT)
                self.assertNotEqual(reuse_port, 0, "SO_REUSEPORT deve estar habilitado na plataforma suportada")

            host, port = sock.getsockname()
            self.assertEqual(host, "127.0.0.1")
            self.assertGreater(port, 0)
        finally:
            sock.close()

    def test_differentiation_listen_process_blocks_vs_timewait_allows(self):
        """Diferenciação precisa entre processo ativo em LISTEN e porta liberável."""
        # 1. Processo alheio ativo em LISTEN (ex: Postgres / Node) com PID identificado -> deve bloquear
        with patch.object(web_server, "inspect_process" if hasattr(web_server, "inspect_process") else "is_port_in_use", return_value=True):
            with patch("subprocess.check_output") as mock_out:
                mock_out.return_value = "55555\n"
                with patch("run_cockpit.inspect_process", return_value=("node", "node index.js")):
                    can_boot = run_cockpit.handle_port_conflict(port=8765, host="127.0.0.1", force=False)
                    self.assertFalse(can_boot, "handle_port_conflict deve bloquear se outro processo não-cockpit estiver ouvindo")

        # 2. Processo ativo em LISTEN mas lsof não retorna PID (ex: falta de permissão) -> deve bloquear
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        _, port = srv.getsockname()
        srv.listen(1)
        try:
            with patch("subprocess.check_output", return_value=""):
                can_boot_ws = web_server.handle_port_conflict(port=port, host="127.0.0.1", force=False)
                self.assertFalse(
                    can_boot_ws,
                    "web_server.handle_port_conflict não pode liberar a porta se há processo real em LISTEN, mesmo sem PID visível"
                )
                can_boot_rc = run_cockpit.handle_port_conflict(port=port, host="127.0.0.1", force=False)
                self.assertFalse(
                    can_boot_rc,
                    "run_cockpit.handle_port_conflict não pode liberar a porta se há processo real em LISTEN, mesmo sem PID visível"
                )
        finally:
            srv.close()

    def test_uvicorn_initialization_uses_prebound_reusable_socket(self):
        """run_cockpit.start_server deve instanciar Uvicorn passando socket pré-vinculado."""
        self.assertTrue(
            hasattr(run_cockpit, "start_server"),
            "run_cockpit deve expor start_server para inicialização modular do Uvicorn"
        )
        with patch("run_cockpit.create_bound_socket") as mock_create_sock, \
             patch("uvicorn.Server") as mock_server_cls, \
             patch("uvicorn.Config") as mock_config_cls:

            fake_sock = MagicMock()
            mock_create_sock.return_value = fake_sock
            mock_server_instance = MagicMock()
            mock_server_cls.return_value = mock_server_instance

            run_cockpit.start_server(host="127.0.0.1", port=8765)

            mock_create_sock.assert_called_once_with(host="127.0.0.1", port=8765)
            mock_config_cls.assert_called_once()
            mock_server_cls.assert_called_once()
            mock_server_instance.run.assert_called_once_with(sockets=[fake_sock])


if __name__ == "__main__":
    unittest.main()
