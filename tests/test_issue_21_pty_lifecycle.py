import os
import sys
import signal
import asyncio
import unittest
from unittest.mock import MagicMock, patch, call

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from server.pty_manager import PTYSession, PTYSessionManager


class TestIssue21PTYLifecycle(unittest.TestCase):
    def setUp(self):
        self.manager = PTYSessionManager()

    def tearDown(self):
        self.manager.cleanup_all()

    def test_pty_session_supports_lazy_spawn(self):
        """Sessões PTY criadas com lazy=True não devem fazer fork de processos no boot."""
        session = PTYSession(
            session_id="term_lazy_test",
            cwd=BASE_DIR,
            env={"TERM": "xterm-256color"},
            lazy=True
        )
        # Processo não deve ter sido criado ainda
        self.assertIsNone(session.pid, "PID deve ser None para sessões criadas com lazy=True")
        self.assertFalse(session.is_alive, "Sessão lazy não deve estar marcada como alive antes do spawn")
        self.assertFalse(session.is_spawned, "Sessão lazy deve ter is_spawned=False")

        # Spawn sob demanda
        session.spawn()
        self.assertIsNotNone(session.pid, "PID deve existir após spawn()")
        self.assertTrue(session.is_alive, "Sessão deve estar viva após spawn()")
        self.assertTrue(session.is_spawned, "is_spawned deve ser True após spawn()")

        session.close()

    def test_persisted_sessions_loaded_lazily_on_boot(self):
        """Ao inicializar o PTYSessionManager, sessões frias em sessions.json devem ser carregadas em modo lazy."""
        index_file = self.manager.index_file
        import json
        test_data = {
            "term_persisted_cold": {
                "session_id": "term_persisted_cold",
                "cwd": BASE_DIR,
                "cols": 80,
                "rows": 24,
                "created_at": 123456.0,
                "last_active": 123456.0
            }
        }
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        mgr = PTYSessionManager(sessions_dir=self.manager.sessions_dir)
        session = mgr.get_session("term_persisted_cold")
        self.assertIsNotNone(session, "Sessão persistida deve ser carregada")
        self.assertIsNone(session.pid, "Sessão persistida deve ser carregada em modo lazy (sem pid/fork no boot)")
        self.assertFalse(session.is_spawned, "Sessão persistida restaurada não deve estar spawned")
        mgr.cleanup_all()

    def test_close_performs_robust_reaping_with_sigkill_fallback(self):
        """O close() deve tentar SIGTERM com WNOHANG e, se o processo não encerrar, escalonar para SIGKILL."""
        session = PTYSession(
            session_id="term_reap_test",
            cwd=BASE_DIR,
            env={"TERM": "xterm-256color"},
            lazy=True
        )
        # Mock do processo
        session.pid = 99999
        session.master_fd = 100
        session.is_alive = True
        session.is_spawned = True

        kill_calls = []
        def fake_kill(pid, sig):
            kill_calls.append((pid, sig))

        waitpid_calls = []
        # Todas as 5 tentativas com SIGTERM: processo ainda vivo (0, 0)
        # Após SIGKILL: processo coletado (99999, 0)
        waitpid_returns = [(0, 0)] * 5 + [(99999, 0)]
        def fake_waitpid(pid, options):
            waitpid_calls.append((pid, options))
            if waitpid_returns:
                return waitpid_returns.pop(0)
            return (pid, 0)

        with patch("os.close") as mock_close, \
             patch("os.kill", side_effect=fake_kill), \
             patch("os.waitpid", side_effect=fake_waitpid), \
             patch("time.sleep", return_value=None):
            
            session.close()

            # os.close deve ter sido chamado para master_fd
            mock_close.assert_called_with(100)

            # Verifica que SIGTERM foi tentado
            self.assertIn((99999, signal.SIGTERM), kill_calls)
            # Verifica que escalonou para SIGKILL porque waitpid retornou (0, 0)
            self.assertIn((99999, signal.SIGKILL), kill_calls)
            # Verifica que waitpid foi chamado com WNOHANG
            self.assertTrue(any(call[1] == os.WNOHANG for call in waitpid_calls))
            self.assertFalse(session.is_alive)

    def test_stop_all_terminates_all_active_sessions(self):
        """stop_all() deve chamar close() em todas as sessões ativas e esvaziar o cache em memória."""
        s1 = self.manager.get_or_create(session_id="term_stop_1", cwd=BASE_DIR)
        s2 = self.manager.get_or_create(session_id="term_stop_2", cwd=BASE_DIR)

        self.assertTrue(s1.is_alive)
        self.assertTrue(s2.is_alive)

        self.manager.stop_all()

        self.assertFalse(s1.is_alive)
        self.assertFalse(s2.is_alive)
        self.assertEqual(len(self.manager._sessions), 0)

    def test_fastapi_shutdown_hook_invokes_pty_stop_all(self):
        """O shutdown_event em web_server.py deve invocar pty_session_manager.stop_all()."""
        import server.web_server as ws

        self.assertIsNotNone(ws.pty_session_manager, "pty_session_manager deve estar disponível no web_server")
        
        with patch.object(ws.pty_session_manager, "stop_all") as mock_stop_all:
            # Executa a rotina de shutdown registrada no web_server
            asyncio.run(ws.shutdown_event())
            mock_stop_all.assert_called_once()


if __name__ == "__main__":
    unittest.main()
