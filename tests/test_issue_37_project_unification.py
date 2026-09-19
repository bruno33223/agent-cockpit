import os
import sys
import json
import shutil
import tempfile
import unittest

_cur_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_cur_dir)
_server_dir = os.path.join(_repo_root, "server")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from state_store import StateStore, StateStoreFacade, canonical_project_id
from storage import StateFacade
import mcp_server


class TestIssue37ProjectUnification(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cockpit_issue37_test_")
        self.test_states_dir = os.path.join(self.temp_dir, "states")
        os.makedirs(self.test_states_dir, exist_ok=True)
        self.store = StateStore(states_dir=self.test_states_dir)
        self._orig_mcp_db = getattr(mcp_server, "db", None)
        mcp_server.db = self.store

    def tearDown(self):
        if self._orig_mcp_db is not None:
            mcp_server.db = self._orig_mcp_db
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_slices_save_in_parent_project_no_ghost_slices_in_index_or_files(self):
        """a) Fatias (slice-1, slice-2) devem salvar dentro do projeto pai e NUNCA criar arquivos slice-*.json nem entradas no índice."""
        real_repo = os.path.join(self.temp_dir, "production_repo")
        os.makedirs(real_repo, exist_ok=True)

        # Importa explicitamente o projeto pai
        import_res = self.store.import_project(project_path=real_repo, name="Production Repo", switch=True)
        parent_pid = import_res["project"]["id"]
        self.assertEqual(self.store.get_current_project_id(), parent_pid)

        # Sincroniza épico e fatias
        self.store.sync_epic(
            epic_name="Unified Epic",
            goal="Test Slices Unification",
            vertical_slices=[
                {"id": "slice-1", "title": "Vertical Slice 1", "acceptance_criteria": "Crit 1"},
                {"id": "slice-2", "title": "Vertical Slice 2", "acceptance_criteria": "Crit 2"}
            ],
            project_root=real_repo,
            project_id=parent_pid
        )

        # Executa operações passando slice_id como project_id ou slice_id
        self.store.update_agent_pulse(
            pair_id=1, builder_status="WORKING", critic_status="IDLE",
            slice_id="slice-1", attempt=2, details_md="Trabalhando na slice-1",
            project_id="slice-1"
        )
        self.store.log_critique_verdict(
            slice_id="slice-1", attempt=2, verdict="APROVADO",
            reason_md="Validado com louvor", project_id="slice-1"
        )
        self.store.add_user_steering(
            text="Focar em modularidade", project_id="slice-1", slice_id="slice-1"
        )
        self.store.register_fleet_anomaly(
            slice_id="slice-2", anomaly_type="STALLED", details="Slice 2 parada",
            project_id="slice-2"
        )

        # 1. Verifica estado do projeto pai
        parent_state = self.store.get_state(parent_pid)
        nodes = parent_state.get("nodes", [])
        node1 = next((n for n in nodes if n.get("id") == "slice-1"), None)
        self.assertIsNotNone(node1, "slice-1 deve residir na lista nodes do projeto pai")
        self.assertEqual(node1.get("kanban_status"), "APPROVED")
        self.assertEqual(node1.get("attempt"), 2)

        node2 = next((n for n in nodes if n.get("id") == "slice-2"), None)
        self.assertIsNotNone(node2, "slice-2 deve residir na lista nodes do projeto pai")
        self.assertEqual(node2.get("kanban_status"), "STALLED")

        # 2. projects_index.json NÃO deve ter nenhuma fatia como projeto autônomo
        index_data = self.store._read_index()
        projects_dict = index_data.get("projects", {})
        for pid in projects_dict.keys():
            self.assertFalse(pid.startswith("slice-"), f"Entrada de fatia encontrada no projects_index: {pid}")

        # 3. test_states_dir NÃO deve ter arquivos slice-*.json
        files_in_states = os.listdir(self.test_states_dir)
        ghost_slice_files = [f for f in files_in_states if f.startswith("slice-")]
        self.assertEqual(ghost_slice_files, [], f"Arquivos de fatia encontrados em states/: {ghost_slice_files}")

    def test_explicit_project_import_validation(self):
        """b) Importação explícita de projeto: valida diretório real, caminho canônico e rejeita pastas inexistentes ou arquivos."""
        valid_dir = os.path.join(self.temp_dir, "legit_project")
        os.makedirs(valid_dir, exist_ok=True)

        # Importação com sucesso
        res = self.store.import_project(project_path=valid_dir)
        self.assertEqual(res["status"], "ok")
        proj_meta = res["project"]
        self.assertEqual(proj_meta["name"], "legit_project")
        self.assertEqual(proj_meta["project_root"], os.path.realpath(valid_dir))
        self.assertEqual(self.store.get_current_project_id(), proj_meta["id"])

        # Rejeita diretório inexistente
        ghost_path = os.path.join(self.temp_dir, "ghost_directory_404")
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.store.import_project(project_path=ghost_path)

        # Rejeita arquivo comum (não diretório)
        fake_file = os.path.join(self.temp_dir, "not_a_folder.txt")
        with open(fake_file, "w") as f:
            f.write("hello")
        with self.assertRaises((ValueError, NotADirectoryError)):
            self.store.import_project(project_path=fake_file)

    def test_reject_or_redirect_slice_registration_as_new_project(self):
        """c) Tentativa de registrar fatias como novos projetos é rejeitada/redirecionada para o projeto ativo."""
        real_repo = os.path.join(self.temp_dir, "active_repo")
        os.makedirs(real_repo, exist_ok=True)
        res = self.store.import_project(project_path=real_repo, switch=True)
        active_pid = res["project"]["id"]

        # resolve_project_id com padrões de fatia deve retornar active_pid
        self.assertEqual(self.store.resolve_project_id("slice-1"), active_pid)
        self.assertEqual(self.store.resolve_project_id("slice-42"), active_pid)
        self.assertEqual(self.store.resolve_project_id("slice-auth-module"), active_pid)
        self.assertEqual(self.store.resolve_project_id("slice-builder-frontend"), active_pid)

        # worktree path contendo .worktrees deve resolver para a raiz do repositório
        wt_path = os.path.join(real_repo, ".worktrees", "slice-1")
        self.assertEqual(self.store.resolve_project_id(wt_path), active_pid)

        # Tentativa direta de gravar estado com ID de fatia não cria slice-*.json
        self.store._save_state({"nodes": []}, project_id="slice-1")
        files = os.listdir(self.test_states_dir)
        self.assertFalse(any(f.startswith("slice-") for f in files))
        index = self.store._read_index()
        self.assertNotIn("slice-1", index.get("projects", {}))

    def test_test_isolation_via_cockpit_states_dir(self):
        """d) Isolamento de testes via COCKPIT_STATES_DIR: operações de teste não afetam a pasta states de produção."""
        isolated_dir = os.path.join(self.temp_dir, "isolated_states")
        os.makedirs(isolated_dir, exist_ok=True)

        old_env = os.environ.get("COCKPIT_STATES_DIR")
        try:
            os.environ["COCKPIT_STATES_DIR"] = isolated_dir
            isolated_store = StateStoreFacade(states_dir=isolated_dir)
            
            repo = os.path.join(self.temp_dir, "isolated_repo")
            os.makedirs(repo, exist_ok=True)
            isolated_store.import_project(repo)

            # Arquivos devem estar apenas em isolated_dir
            self.assertTrue(os.path.exists(os.path.join(isolated_dir, "projects_index.json")))
            self.assertEqual(len(os.listdir(isolated_dir)) >= 2, True)

            # Verifica que a pasta states oficial não foi afetada por este isolated_repo
            official_states_dir = os.path.abspath(os.path.join(_repo_root, "states"))
            if os.path.exists(official_states_dir):
                with open(os.path.join(official_states_dir, "projects_index.json"), "r") as f:
                    prod_index = json.load(f)
                self.assertNotIn("isolated_repo", [p.get("name") for p in prod_index.get("projects", {}).values()])
        finally:
            if old_env is not None:
                os.environ["COCKPIT_STATES_DIR"] = old_env
            else:
                os.environ.pop("COCKPIT_STATES_DIR", None)

    def test_purge_stale_and_temp_projects(self):
        """e) Rotina de purga limpa projetos órfãos de /tmp do índice e remove arquivos slice-*.json órfãos."""
        # Cria projeto legítimo
        legit_repo = os.path.join(self.temp_dir, "keep_this_repo")
        os.makedirs(legit_repo, exist_ok=True)
        res = self.store.import_project(project_path=legit_repo, switch=True)
        legit_pid = res["project"]["id"]

        # Polui deliberadamente o index e arquivos com projetos /tmp e fatias
        index_data = self.store._read_index()
        projects = index_data.setdefault("projects", {})
        
        # 3 projetos fantasmas em /tmp
        ghost_ids = ["ghost-tmp-1", "ghost-tmp-2", "ghost-tmp-3"]
        for gid in ghost_ids:
            projects[gid] = {
                "id": gid,
                "name": f"Ghost {gid}",
                "project_root": f"/tmp/cockpit_issue20_test_random_{gid}/proj",
                "total_slices": 1
            }
            ghost_file = os.path.join(self.test_states_dir, f"{gid}.json")
            with open(ghost_file, "w") as f:
                json.dump({"epic": {"name": gid}}, f)

        # 2 projetos fantasmas com ID de fatia
        slice_ids = ["slice-1-legacy", "slice-2-legacy"]
        for sid in slice_ids:
            projects[sid] = {
                "id": sid,
                "name": sid,
                "project_root": None,
                "total_slices": 1
            }
            slice_file = os.path.join(self.test_states_dir, f"{sid}.json")
            with open(slice_file, "w") as f:
                json.dump({"slice": sid}, f)

        # 1 arquivo slice órfão solto em states/
        orphan_slice_file = os.path.join(self.test_states_dir, "slice-3-orphan.json")
        with open(orphan_slice_file, "w") as f:
            f.write("{}")

        self.store._save_index(index_data)

        # Executa a rotina de purga
        purge_report = self.store.purge_stale_or_temp_projects()

        # Verifica relatório
        self.assertIn("purged_projects", purge_report)
        self.assertTrue(len(purge_report["purged_projects"]) >= 5)

        # Verifica índice limpo
        cleaned_index = self.store._read_index()
        cleaned_projects = cleaned_index.get("projects", {})
        self.assertIn(legit_pid, cleaned_projects, "Projeto legítimo deve ser mantido")
        for gid in ghost_ids:
            self.assertNotIn(gid, cleaned_projects, f"Projeto fantasma {gid} deveria ter sido purgado")
        for sid in slice_ids:
            self.assertNotIn(sid, cleaned_projects, f"Projeto fatia {sid} deveria ter sido purgado")

        # Verifica arquivos físicos removidos
        remaining_files = os.listdir(self.test_states_dir)
        self.assertFalse(any(f.startswith("slice-") for f in remaining_files), "Nenhum arquivo slice-*.json deve restar")
        for gid in ghost_ids:
            self.assertFalse(os.path.exists(os.path.join(self.test_states_dir, f"{gid}.json")))

    def test_api_endpoints_import_and_purge(self):
        """Testa endpoints FastAPI /api/projects/import e /api/projects/purge com injeção de db de teste."""
        import routers.telemetry as tm
        from routers.telemetry import import_project_endpoint, purge_projects_endpoint, ImportProjectPayload
        from fastapi import HTTPException

        orig_db = tm.db
        tm.db = self.store
        try:
            # 1. Importação válida via endpoint
            api_repo = os.path.join(self.temp_dir, "api_test_repo")
            os.makedirs(api_repo, exist_ok=True)
            res = import_project_endpoint(ImportProjectPayload(path=api_repo, name="API Repo", switch=True))
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["project"]["name"], "API Repo")

            # 2. Importação inválida via endpoint levanta HTTPException 400
            invalid_path = os.path.join(self.temp_dir, "non_existent_folder_abc")
            with self.assertRaises(HTTPException) as ctx:
                import_project_endpoint(ImportProjectPayload(path=invalid_path))
            self.assertEqual(ctx.exception.status_code, 400)

            # 3. Purga via endpoint
            purge_res = purge_projects_endpoint()
            self.assertEqual(purge_res["status"], "ok")
            self.assertIn("report", purge_res)
        finally:
            tm.db = orig_db


if __name__ == "__main__":
    unittest.main()
