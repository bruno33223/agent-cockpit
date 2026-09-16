import os
import sys
import tempfile
import shutil
import unittest
import json

# Ajusta sys.path para importar módulos do servidor
_cur_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_cur_dir)
_server_dir = os.path.join(_repo_root, "server")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from state_store import StateStore, canonical_project_id
import mcp_server

class TestIssue20RootResolution(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cockpit_issue20_test_")
        self.states_dir = os.path.join(self.temp_dir, "states")
        os.makedirs(self.states_dir, exist_ok=True)
        self.store = StateStore(states_dir=self.states_dir)
        
        self._orig_mcp_db = mcp_server.db
        mcp_server.db = self.store

    def tearDown(self):
        mcp_server.db = self._orig_mcp_db
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_reset_state_preserves_project_root(self):
        """reset_state deve preservar o project_root e não zerar para None."""
        project_root_path = os.path.join(self.temp_dir, "my_awesome_project")
        os.makedirs(project_root_path, exist_ok=True)
        
        pid = canonical_project_id(project_root_path)
        self.store.sync_epic(
            epic_name="Awesome Epic",
            goal="Test Goal",
            vertical_slices=[
                {"id": "slice-1", "title": "Slice 1", "acceptance_criteria": "Crit 1"},
                {"id": "slice-2", "title": "Slice 2", "acceptance_criteria": "Crit 2"}
            ],
            project_root=project_root_path,
            project_id=pid
        )

        initial_state = self.store.get_state(pid)
        self.assertEqual(initial_state.get("project_root"), project_root_path)

        # Executa reset_state
        reset_res = self.store.reset_state(pid)
        self.assertIsNotNone(reset_res.get("project_root"), "project_root não deve ser None após reset_state")
        self.assertEqual(reset_res.get("project_root"), project_root_path)

        fetched_state = self.store.get_state(pid)
        self.assertEqual(fetched_state.get("project_root"), project_root_path)
        self.assertEqual(self.store.get_project_root(pid), project_root_path)

    def test_slice_updates_resolve_parent_project_no_ghost_slices(self):
        """Worktree paths (.worktrees/slice-N) devem resolver para o projeto principal, evitando arquivos fantasma."""
        parent_project = os.path.join(self.temp_dir, "sample_repo")
        worktree_slice2 = os.path.join(parent_project, ".worktrees", "slice-2")
        os.makedirs(worktree_slice2, exist_ok=True)

        parent_pid = canonical_project_id(parent_project)
        self.store.sync_epic(
            epic_name="Sample Project",
            goal="Goal Sample",
            vertical_slices=[
                {"id": "slice-1", "title": "Slice 1", "acceptance_criteria": "Crit 1"},
                {"id": "slice-2", "title": "Slice 2", "acceptance_criteria": "Crit 2"}
            ],
            project_root=parent_project,
            project_id=parent_pid
        )
        self.store.switch_current_project(parent_pid)

        # 1. canonical_project_id a partir do worktree_slice2 deve retornar o parent_pid
        resolved_pid = canonical_project_id(worktree_slice2)
        self.assertEqual(resolved_pid, parent_pid, "Worktree path deve resolver para o ID canônico do projeto pai")

        # 2. Chamada de ferramenta MCP vinda da worktree com working_dir da fatia
        resp = mcp_server.handle_tool_call("update_agent_pulse", {
            "pair_id": 2,
            "builder_status": "WORKING",
            "critic_status": "IDLE",
            "slice_id": "slice-2",
            "working_dir": worktree_slice2
        })
        self.assertNotIn("error", str(resp))

        # 3. Verifica que nenhum arquivo fantasma de slice foi criado em states/
        state_files = os.listdir(self.states_dir)
        ghost_files = [f for f in state_files if f.startswith("slice-")]
        self.assertEqual(ghost_files, [], f"Nenhum arquivo fantasma slice-N-*.json deve ser criado, mas encontrou: {ghost_files}")

        # 4. Verifica que o nó no projeto pai foi atualizado
        parent_state = self.store.get_state(parent_pid)
        pair2 = next((p for p in parent_state.get("pairs_3x3", []) if p.get("id") == 2), None)
        self.assertIsNotNone(pair2)
        self.assertEqual(pair2.get("builder_status"), "WORKING")

    def test_verify_completion_evidence_locates_test_raw_log_canonically(self):
        """verify_completion_evidence deve localizar TEST_RAW.log no diretório canônico da blueprint do project_root."""
        parent_project = os.path.join(self.temp_dir, "canonical_bp_project")
        bp_dir = os.path.join(parent_project, "cockpit-agent", "blueprints", "01_release")
        os.makedirs(bp_dir, exist_ok=True)

        raw_log_path = os.path.join(bp_dir, "TEST_RAW.log")
        with open(raw_log_path, "w", encoding="utf-8") as f:
            f.write("=== TEST RUN: pytest ===\nExit Code: 0\nAll tests passed!\n")

        pid = canonical_project_id(parent_project)
        self.store.sync_epic(
            epic_name="Canonical BP Project",
            goal="Verify Raw Log Location",
            vertical_slices=[
                {"id": "slice-1", "title": "Slice 1", "acceptance_criteria": "Crit 1"},
                {"id": "slice-2", "title": "Slice 2", "acceptance_criteria": "Crit 2"}
            ],
            project_root=parent_project,
            project_id=pid
        )
        self.store.switch_current_project(pid)

        # Executa verify_completion_evidence sem passar caminho absoluto de TEST_RAW.log
        resp = mcp_server.handle_tool_call("verify_completion_evidence", {
            "slice_id": "slice-2",
            "project_id": pid
        })
        data = json.loads(resp["content"][0]["text"])
        
        self.assertTrue(data.get("compliant"), f"Deveria ter compliance True, mas recebeu: {data}")
        self.assertEqual(data.get("exit_code"), 0)
        self.assertEqual(os.path.abspath(data.get("log_path")), os.path.abspath(raw_log_path))

if __name__ == "__main__":
    unittest.main()
