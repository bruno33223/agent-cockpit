import os
import sys
import json
import time
import tempfile
import unittest
from unittest.mock import MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from server.pty_manager import PTYSessionManager, PTYSession

class TestIssue8ConcurrentSpecializedTerminals(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = PTYSessionManager(sessions_dir=self.temp_dir.name)

        self.js_path = os.path.join(BASE_DIR, "web", "js", "terminal_workspace.js")
        with open(self.js_path, "r", encoding="utf-8") as f:
            self.js_content = f.read()

        self.css_path = os.path.join(BASE_DIR, "web", "styles.css")
        with open(self.css_path, "r", encoding="utf-8") as f:
            self.css_content = f.read()

    def tearDown(self):
        self.manager.cleanup_all()
        self.temp_dir.cleanup()

    def test_role_specialization_in_backend(self):
        """Critério 1: Separação clara e categorização por papel (Orquestrador, Agente, Subagente)."""
        # 1. Orquestrador Staff
        s_orch = self.manager.get_or_create(
            session_id="term_orch_1",
            cwd=BASE_DIR,
            project_id="proj-alpha",
            role="orchestrator",
            name="Orquestrador Staff"
        )
        self.assertEqual(s_orch.role, "orchestrator")
        self.assertEqual(s_orch.name, "Orquestrador Staff")

        # 2. Agente da Frota / Slice
        s_agent = self.manager.get_or_create(
            session_id="term_agent_slice1",
            cwd=BASE_DIR,
            project_id="proj-alpha",
            role="agent",
            name="Agente Executor (slice-1)",
            slice_id="slice-1",
            task_id="slice-1"
        )
        self.assertEqual(s_agent.role, "agent")
        self.assertEqual(s_agent.slice_id, "slice-1")

        # 3. Subagente Efêmero vinculado a tarefa
        s_sub = self.manager.get_or_create(
            session_id="term_sub_task42",
            cwd=BASE_DIR,
            project_id="proj-alpha",
            role="subagent",
            name="Subagente Pesquisa",
            task_id="task-42"
        )
        self.assertEqual(s_sub.role, "subagent")
        self.assertEqual(s_sub.task_id, "task-42")

        # Filtro por contexto e papel
        orch_sessions = self.manager.get_sessions_by_context(project_id="proj-alpha", role="orchestrator")
        self.assertEqual(len(orch_sessions), 1)
        self.assertEqual(orch_sessions[0].session_id, "term_orch_1")

        agent_sessions = self.manager.get_sessions_by_context(project_id="proj-alpha", role="agent")
        self.assertEqual(len(agent_sessions), 1)
        self.assertEqual(agent_sessions[0].session_id, "term_agent_slice1")

        sub_sessions = self.manager.get_sessions_by_context(project_id="proj-alpha", role="subagent")
        self.assertEqual(len(sub_sessions), 1)
        self.assertEqual(sub_sessions[0].session_id, "term_sub_task42")

    def test_durable_disk_persistence_across_reboots(self):
        """Critério: Terminais e histórico sobrevivem à reinicialização da aplicação ou máquina."""
        # Cria sessão com histórico no manager 1
        s1 = self.manager.get_or_create(
            session_id="term_reboot_test",
            cwd=BASE_DIR,
            project_id="proj-persisted",
            role="orchestrator",
            name="Orquestrador Persistente"
        )
        
        # Simula escrita no log
        log_path = self.manager._get_log_path("term_reboot_test")
        self.assertTrue(os.path.exists(self.manager.index_file))
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("primeiro_comando_executado\r\n")
            f.write("resultado_do_comando_alpha\r\n")

        # Simula encerramento do processo do manager (reboot/shutdown da aplicação)
        self.manager.stop_all()

        # Instancia um NOVO manager apontando para o mesmo diretório de sessões persistidas
        restored_manager = PTYSessionManager(sessions_dir=self.temp_dir.name)
        
        restored_session = restored_manager.get_session("term_reboot_test")
        self.assertIsNotNone(restored_session, "A sessão deve ser restaurada do disco")
        self.assertEqual(restored_session.role, "orchestrator")
        self.assertEqual(restored_session.name, "Orquestrador Persistente")
        self.assertEqual(restored_session.project_id, "proj-persisted")

        # Valida que o histórico prévio foi carregado intacto
        mock_ws = MagicMock()
        history = restored_session.attach(mock_ws)
        self.assertIn("primeiro_comando_executado", history)
        self.assertIn("resultado_do_comando_alpha", history)
        self.assertIn("Sessão restaurada", history)

        restored_manager.cleanup_all()

    def test_subagent_clean_termination(self):
        """Critério 3: Subagentes podem ser vinculados a tarefas específicas e encerrados de forma limpa."""
        s_sub = self.manager.get_or_create(
            session_id="subagent_to_kill",
            cwd=BASE_DIR,
            project_id="proj-alpha",
            role="subagent",
            task_id="task-99"
        )
        self.assertIn("subagent_to_kill", [s["session_id"] for s in self.manager.list_sessions()])
        
        # Encerramento limpo
        closed = self.manager.close_session("subagent_to_kill")
        self.assertTrue(closed)
        self.assertNotIn("subagent_to_kill", [s["session_id"] for s in self.manager.list_sessions()])
        self.assertIsNone(self.manager.get_session("subagent_to_kill"))

    def test_frontend_roles_and_chrome_tabs_structure(self):
        """Critério 2: Valida suporte a badges de papel, abas estilo Chrome e statusline de permissões."""
        # Valida helpers de papéis no JS
        self.assertIn("getRoleIcon(role)", self.js_content)
        self.assertIn("getRoleTitle(role)", self.js_content)
        self.assertIn("getRoleBadgeHtml(role)", self.js_content)
        self.assertIn("getRolePermissionsText(role)", self.js_content)
        self.assertIn("Staff Orchestrator (Full Access / Blueprint Control)", self.js_content)
        self.assertIn("Fleet Agent (Worktree Isolated / Auto-Red-Green)", self.js_content)
        self.assertIn("Ephemeral Subagent (Task Sandbox / Read-Write)", self.js_content)

        # Valida botões e menus de criação especializada
        self.assertIn("initTabsBarControls()", self.js_content)
        self.assertIn("terminal-role-filters", self.js_content)
        self.assertIn("syncSessionsWithBackend", self.js_content)
        self.assertIn("orca-btn-terminate-subagent", self.js_content)

        # Valida estilos CSS para Chrome tabs e badges
        self.assertIn(".term-tab-role-badge.role-orchestrator", self.css_content)
        self.assertIn(".term-tab-role-badge.role-agent", self.css_content)
        self.assertIn(".term-tab-role-badge.role-subagent", self.css_content)
        self.assertIn(".terminal-role-filters", self.css_content)
        self.assertIn(".term-filter-chip", self.css_content)
        self.assertIn(".terminal-add-dropdown", self.css_content)

    def test_terminal_rest_api_lifecycle(self):
        """Valida criação via POST, listagem via GET e deleção via DELETE dos handlers da API REST."""
        from server.web_server import create_terminal_session, get_terminal_sessions, delete_terminal_session

        # 1. Criação de sessão especializada via endpoint POST
        payload = {
            "session_id": "test_api_subagent_direct",
            "project_id": "proj-api",
            "role": "subagent",
            "name": "Subagente Teste API",
            "task_id": "task-api-123"
        }
        res_post = create_terminal_session(payload)
        self.assertEqual(res_post["session_id"], "test_api_subagent_direct")
        self.assertEqual(res_post["role"], "subagent")
        self.assertEqual(res_post["task_id"], "task-api-123")

        # 2. Listagem com filtro de papel via endpoint GET
        sessions = get_terminal_sessions(project_id="proj-api", role="subagent")
        self.assertTrue(any(s["session_id"] == "test_api_subagent_direct" for s in sessions))

        # 3. Encerramento limpo via endpoint DELETE
        res_del = delete_terminal_session("test_api_subagent_direct")
        self.assertEqual(res_del["status"], "ok")
        self.assertTrue(res_del["closed"])

        # 4. Confirmação de remoção da lista
        sessions_after = get_terminal_sessions(project_id="proj-api")
        self.assertFalse(any(s["session_id"] == "test_api_subagent_direct" for s in sessions_after))

if __name__ == "__main__":
    unittest.main()
