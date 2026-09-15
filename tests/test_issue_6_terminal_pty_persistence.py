import os
import sys
import unittest
from unittest.mock import MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from server.pty_manager import PTYSessionManager, PTYSession

class TestIssue6TerminalPTYPersistence(unittest.TestCase):
    def setUp(self):
        self.manager = PTYSessionManager()
        self.html_path = os.path.join(BASE_DIR, "web", "index.html")
        self.js_path = os.path.join(BASE_DIR, "web", "app.js")

        with open(self.js_path, "r", encoding="utf-8") as f:
            self.js_content = f.read()

    def tearDown(self):
        self.manager.cleanup_all()

    def test_backend_pty_mapping_task_1_to_n(self):
        """Critério 1 e 2: Mapeamento Tarefa/Slice -> Múltiplas Sessões PTY (1:N) e persistência em memória."""
        # Cria 2 terminais para a tarefa 'slice-1' do projeto 'proj-a'
        s1 = self.manager.get_or_create(
            session_id="term_slice-1_1",
            cwd=BASE_DIR,
            project_id="proj-a",
            task_id="slice-1"
        )
        s2 = self.manager.get_or_create(
            session_id="term_slice-1_2",
            cwd=BASE_DIR,
            project_id="proj-a",
            task_id="slice-1"
        )

        # Cria 1 terminal para 'slice-2'
        s3 = self.manager.get_or_create(
            session_id="term_slice-2_1",
            cwd=BASE_DIR,
            project_id="proj-a",
            task_id="slice-2"
        )

        self.assertEqual(s1.task_id, "slice-1")
        self.assertEqual(s2.task_id, "slice-1")
        self.assertEqual(s3.task_id, "slice-2")

        # Busca sessões por contexto 1:N
        slice1_sessions = self.manager.get_sessions_by_context(task_id="slice-1")
        self.assertEqual(len(slice1_sessions), 2)
        session_ids = [s.session_id for s in slice1_sessions]
        self.assertIn("term_slice-1_1", session_ids)
        self.assertIn("term_slice-1_2", session_ids)

        slice2_sessions = self.manager.get_sessions_by_context(task_id="slice-2")
        self.assertEqual(len(slice2_sessions), 1)
        self.assertEqual(slice2_sessions[0].session_id, "term_slice-2_1")

    def test_backend_history_buffer_preserved_on_detach(self):
        """Critério 3: Nenhuma perda de buffer ou interrupção de processo ao navegar entre tarefas/projetos."""
        session = self.manager.get_or_create(
            session_id="term_test_buffer",
            cwd=BASE_DIR,
            project_id="proj-alpha",
            task_id="slice-alpha"
        )

        # Simula histórico de buffer
        session.history.append("Output do agente executando testes...\r\n")
        session.history.append("Passo 1 concluído.\r\n")

        # Simula websocket conectando, recebendo histórico e desconectando
        mock_ws = MagicMock()
        history_output = session.attach(mock_ws)
        self.assertIn("Output do agente", history_output)
        self.assertIn("Passo 1 concluído", history_output)

        session.detach(mock_ws)
        self.assertEqual(len(session.active_websockets), 0)

        # Sessão continua viva e com buffer preservado
        mock_ws2 = MagicMock()
        reattached_history = session.attach(mock_ws2)
        self.assertIn("Output do agente", reattached_history)

    def test_frontend_app_js_context_switching_and_persistence(self):
        """Valida que o web/app.js possui isolamento e restauração de sessões 1:N sem comandos forçados de cd."""
        # Deve mapear sessões por contexto (ex: activeContextKey, currentSliceId ou projectId)
        self.assertTrue(
            'activeContextKey' in self.js_content or 'currentContextKey' in self.js_content or 'switchContext' in self.js_content,
            "TerminalWorkspaceManager deve possuir controle de contexto de sessões por tarefa/projeto"
        )
        # Não deve haver o envio indiscriminado de sendTerminalCommand(`cd ...`) ao clicar em cards
        self.assertNotIn('sendTerminalCommand(`cd "${proj.project_root}"\\n`)', self.js_content)

if __name__ == "__main__":
    unittest.main()
