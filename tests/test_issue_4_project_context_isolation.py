import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock

# Ajusta sys.path para importar módulos do servidor
_cur_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_cur_dir)
_server_dir = os.path.join(_repo_root, "server")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from state_store import StateStore
import web_server
import mcp_server

class TestIssue4ProjectContextIsolation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cockpit_issue4_test_")
        self.store = StateStore(states_dir=self.temp_dir)
        # Substitui temporariamente a instância db do web_server e mcp_server
        self._orig_web_db = web_server.db
        self._orig_mcp_db = mcp_server.db
        web_server.db = self.store
        mcp_server.db = self.store

    def tearDown(self):
        web_server.db = self._orig_web_db
        mcp_server.db = self._orig_mcp_db
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_state_always_includes_active_project_id(self):
        """Requisito 1: Sincronização de Estado unificada em torno de state.active_project_id"""
        state_default = self.store.get_state()
        self.assertIn("active_project_id", state_default)
        self.assertIn("project_id", state_default)
        self.assertEqual(state_default["active_project_id"], "default")
        self.assertEqual(state_default["project_id"], "default")

        # Projeto customizado
        state_proj_x = self.store.get_state("proj_alpha")
        self.assertEqual(state_proj_x["active_project_id"], "proj_alpha")
        self.assertEqual(state_proj_x["project_id"], "proj_alpha")

    def test_project_data_strict_isolation(self):
        """Requisito 2: Zero vazamento de dados cruzados entre projetos."""
        # Configura Proj A
        self.store.sync_epic(
            epic_name="Épico Alpha",
            goal="Objetivo do Projeto Alpha",
            vertical_slices=[
                {"id": "slice-alpha-1", "title": "Fatia Alpha 1", "acceptance_criteria": "Critério A"}
            ],
            project_id="proj_alpha"
        )
        self.store.add_user_steering("Mensagem apenas para Alpha", project_id="proj_alpha")
        self.store.log_critique_verdict(
            slice_id="slice-alpha-1",
            attempt=1,
            verdict="APROVADO",
            reason_md="Validação Alpha",
            project_id="proj_alpha"
        )

        # Configura Proj B
        self.store.sync_epic(
            epic_name="Épico Beta",
            goal="Objetivo do Projeto Beta",
            vertical_slices=[
                {"id": "slice-beta-1", "title": "Fatia Beta 1", "acceptance_criteria": "Critério B"}
            ],
            project_id="proj_beta"
        )
        self.store.add_user_steering("Mensagem apenas para Beta", project_id="proj_beta")
        self.store.log_critique_verdict(
            slice_id="slice-beta-1",
            attempt=1,
            verdict="REJEITADO",
            reason_md="Validação Beta",
            project_id="proj_beta"
        )

        # Verificação Alpha
        state_a = self.store.get_state("proj_alpha")
        self.assertEqual(state_a["epic"]["name"], "Épico Alpha")
        node_ids_a = [n["id"] for n in state_a["nodes"]]
        self.assertIn("slice-alpha-1", node_ids_a)
        self.assertNotIn("slice-beta-1", node_ids_a)
        self.assertTrue(any("Alpha" in m["text"] for m in state_a["steering_messages"]))
        self.assertFalse(any("Beta" in m["text"] for m in state_a["steering_messages"]))
        self.assertEqual(state_a["gauntlet_log"][0]["slice_id"], "slice-alpha-1")
        self.assertEqual(state_a["gauntlet_log"][0]["verdict"], "APROVADO")

        # Verificação Beta
        state_b = self.store.get_state("proj_beta")
        self.assertEqual(state_b["epic"]["name"], "Épico Beta")
        node_ids_b = [n["id"] for n in state_b["nodes"]]
        self.assertIn("slice-beta-1", node_ids_b)
        self.assertNotIn("slice-alpha-1", node_ids_b)
        self.assertTrue(any("Beta" in m["text"] for m in state_b["steering_messages"]))
        self.assertFalse(any("Alpha" in m["text"] for m in state_b["steering_messages"]))
        self.assertEqual(state_b["gauntlet_log"][0]["slice_id"], "slice-beta-1")
        self.assertEqual(state_b["gauntlet_log"][0]["verdict"], "REJEITADO")

    def test_backend_switch_project_endpoint(self):
        """Requisito 3: Disparo de /api/projects/switch atualiza contexto no backend e retorna state sincronizado."""
        # Cria projeto alvo
        self.store.sync_epic(
            epic_name="Projeto Dashboard Switch",
            goal="Testar endpoint switch",
            vertical_slices=[{"id": "slice-1", "title": "Fatia 1"}],
            project_id="proj_switch_target"
        )

        payload = web_server.SwitchProjectPayload(project_id="proj_switch_target")
        data = web_server.post_switch_project(payload)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["current_project_id"], "proj_switch_target")
        self.assertIn("state", data)
        self.assertEqual(data["state"]["active_project_id"], "proj_switch_target")
        self.assertEqual(self.store.get_current_project_id(), "proj_switch_target")

    def test_mcp_server_respects_switched_project(self):
        """Requisito 3: Chamadas MCP devem adotar o projeto ativo no backend quando não especificarem project_root."""
        self.store.sync_epic(
            epic_name="Projeto MCP Target",
            goal="Testar MCP",
            vertical_slices=[{"id": "slice-mcp-1", "title": "Fatia MCP"}],
            project_id="proj_mcp_active"
        )
        self.store.switch_current_project("proj_mcp_active")

        # Testa a resolução interna do MCP Server
        target_pid = mcp_server._resolve_target_project({})
        self.assertEqual(target_pid, "proj_mcp_active")

    def test_frontend_switch_project_implementation(self):
        """Valida que o web/app.js implementa as chamadas necessárias para a Issue 4."""
        app_js_path = os.path.join(_repo_root, "web", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. switchProject deve disparar POST /api/projects/switch
        self.assertIn("'/api/projects/switch'", content)
        # 2. Deve persistir cockpit_project_id e unificar active_project_id
        self.assertIn("state.active_project_id", content)
        # 3. Deve chamar fileExplorerManager.loadFileTree e terminalWorkspace.onProjectSwitched
        self.assertIn("terminalWorkspace.onProjectSwitched", content)
        self.assertIn("fileExplorerManager.loadFileTree", content)
        # 4. Deve invocar recordRecentProject na troca
        self.assertIn("recordRecentProject", content)


if __name__ == "__main__":
    unittest.main()
