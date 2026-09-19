"""
Testes de Arquitetura e Regressão para a Issue #33:
Desacoplamento do State Store e Ferramentas do Local Builder em Camadas de Repositório e Serviços.
"""

import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestIssue33StateAndBuilderRefactor(unittest.TestCase):
    """
    Testes de arquitetura para a Issue #33:
    1. Existência e integridade dos novos módulos em server/storage/ e server/tools/local_builder/
    2. Contagem rígida de linhas (SLOC <= 300 linhas por arquivo)
    3. Retrocompatibilidade total com state_store e tools.local_builder_tool
    4. Integridade funcional de persistência e geração de patches/builder
    """

    EXPECTED_STORAGE_FILES = [
        "__init__.py",
        "project_repository.py",
        "slice_repository.py",
        "settings_repository.py",
        "state_facade.py",
    ]

    EXPECTED_BUILDER_FILES = [
        "__init__.py",
        "surgical_patcher.py",
        "circuit_breaker.py",
        "builder_service.py",
    ]

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cockpit_issue33_")
        self.states_dir = os.path.join(self.temp_dir, "states")
        os.makedirs(self.states_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_modules_existence_and_separation(self):
        """(Critério 1) Novos módulos devem existir nas respectivas pastas com separação de responsabilidades."""
        storage_dir = os.path.join(SERVER_DIR, "storage")
        self.assertTrue(os.path.isdir(storage_dir), f"Diretório {storage_dir} deve existir.")
        for fname in self.EXPECTED_STORAGE_FILES:
            fpath = os.path.join(storage_dir, fname)
            self.assertTrue(os.path.isfile(fpath), f"Arquivo obrigatório não encontrado: {fpath}")

        builder_dir = os.path.join(SERVER_DIR, "tools", "local_builder")
        self.assertTrue(os.path.isdir(builder_dir), f"Diretório {builder_dir} deve existir.")
        for fname in self.EXPECTED_BUILDER_FILES:
            fpath = os.path.join(builder_dir, fname)
            self.assertTrue(os.path.isfile(fpath), f"Arquivo obrigatório não encontrado: {fpath}")

    def test_02_sloc_limit_per_file(self):
        """(Critério 2) Nenhum arquivo resultante pode exceder 300 linhas."""
        files_to_check = []

        # server/storage/
        storage_dir = os.path.join(SERVER_DIR, "storage")
        if os.path.isdir(storage_dir):
            for fname in os.listdir(storage_dir):
                if fname.endswith(".py"):
                    files_to_check.append(os.path.join(storage_dir, fname))

        # server/tools/local_builder/
        builder_dir = os.path.join(SERVER_DIR, "tools", "local_builder")
        if os.path.isdir(builder_dir):
            for fname in os.listdir(builder_dir):
                if fname.endswith(".py"):
                    files_to_check.append(os.path.join(builder_dir, fname))

        # Fachadas de compatibilidade
        files_to_check.append(os.path.join(SERVER_DIR, "state_store.py"))
        files_to_check.append(os.path.join(SERVER_DIR, "tools", "local_builder_tool.py"))

        self.assertGreater(len(files_to_check), 5, "Arquivos para validação de SLOC não encontrados.")

        for fpath in files_to_check:
            self.assertTrue(os.path.exists(fpath), f"Arquivo para checagem de linhas ausente: {fpath}")
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                line_count = len(lines)
            rel_path = os.path.relpath(fpath, REPO_ROOT)
            self.assertLessEqual(
                line_count,
                300,
                f"Arquivo {rel_path} possui {line_count} linhas, excedendo o teto de 300 linhas!"
            )

    def test_03_state_store_retrocompatibility(self):
        """(Critério 3a) server/state_store.py deve manter 100% de retrocompatibilidade com db e StateStore."""
        import state_store
        from state_store import db, StateStore, canonical_project_id, default_initial_state

        self.assertIsNotNone(db)
        self.assertIsNotNone(StateStore)
        self.assertTrue(callable(canonical_project_id))
        self.assertTrue(callable(default_initial_state))

        # Instanciação isolada de StateStore com states_dir personalizado
        store = StateStore(states_dir=self.states_dir)
        self.assertTrue(hasattr(store, "get_state"))
        self.assertTrue(hasattr(store, "sync_epic"))
        self.assertTrue(hasattr(store, "update_agent_pulse"))
        self.assertTrue(hasattr(store, "log_critique_verdict"))
        self.assertTrue(hasattr(store, "add_user_steering"))
        self.assertTrue(hasattr(store, "fetch_unconsumed_steering"))
        self.assertTrue(hasattr(store, "get_governance_settings"))
        self.assertTrue(hasattr(store, "approve_gate"))
        self.assertTrue(hasattr(store, "get_gate_status"))
        self.assertTrue(hasattr(store, "get_project_settings"))
        self.assertTrue(hasattr(store, "set_project_settings"))
        self.assertTrue(hasattr(store, "prune_session_context"))
        self.assertTrue(hasattr(store, "reset_state"))
        self.assertTrue(hasattr(store, "check_fleet_liveness"))
        self.assertTrue(hasattr(store, "resume_orchestration"))
        self.assertTrue(hasattr(store, "file_path"))
        self.assertTrue(hasattr(store, "_file_lock"))
        self.assertTrue(hasattr(store, "_atomic_write_json"))

    def test_04_local_builder_retrocompatibility(self):
        """(Critério 3b) server/tools/local_builder_tool.py deve manter retrocompatibilidade com execute_local_builder e LocalBuilder."""
        import tools.local_builder_tool as lbt
        from tools.local_builder_tool import (
            execute_local_builder,
            LocalBuilder,
            apply_surgical_patch,
            build_local_prompt,
            call_local_llm,
            call_omniroute_llm,
            is_local_llm_recoverable_failure,
            resolve_safe_worktree_path,
            get_worker_queue_status,
            manage_local_model,
        )

        self.assertTrue(callable(execute_local_builder))
        self.assertTrue(callable(apply_surgical_patch))
        self.assertTrue(callable(build_local_prompt))
        self.assertTrue(callable(call_local_llm))
        self.assertTrue(callable(call_omniroute_llm))
        self.assertTrue(callable(is_local_llm_recoverable_failure))
        self.assertTrue(callable(resolve_safe_worktree_path))
        self.assertTrue(callable(get_worker_queue_status))
        self.assertTrue(callable(manage_local_model))
        self.assertTrue(callable(LocalBuilder))

    def test_05_state_persistence_functional_integrity(self):
        """(Critério 4a) Validação funcional ponta a ponta dos novos repositórios de estado."""
        from storage.state_facade import StateFacade

        store = StateFacade(states_dir=self.states_dir)
        pid = "proj-test-issue33"

        # 1. Sincronização de épico
        state = store.sync_epic(
            epic_name="Refatoração Issue 33",
            goal="Desacoplamento em Repositórios",
            vertical_slices=[
                {"id": "slice-1", "title": "Storage Repositories", "max_attempts": 3},
                {"id": "slice-2", "title": "Builder Domain Service", "max_attempts": 3}
            ],
            project_id=pid
        )
        self.assertEqual(state["epic"]["name"], "Refatoração Issue 33")
        self.assertEqual(len(state["nodes"]), 2)

        # 2. Pulse de agente
        pulse_res = store.update_agent_pulse(
            pair_id=1,
            builder_status="WORKING",
            critic_status="IDLE",
            slice_id="slice-1",
            details_md="Iniciando TDD RED",
            project_id=pid
        )
        self.assertEqual(pulse_res["nodes"][0]["kanban_status"], "EXECUTING")

        # 3. Veredito de crítica
        verdict = store.log_critique_verdict(
            slice_id="slice-1",
            attempt=1,
            verdict="APROVADO",
            reason_md="Arquitetura limpa e testes passando",
            project_id=pid
        )
        self.assertEqual(verdict["verdict"], "APROVADO")
        self.assertEqual(store.get_state(pid)["nodes"][0]["kanban_status"], "APPROVED")

        # 4. Steering de usuário
        msg = store.add_user_steering("Manter teto de 300 linhas", project_id=pid, slice_id="slice-1")
        self.assertFalse(msg["consumed"])
        unconsumed = store.fetch_unconsumed_steering(project_id=pid, slice_id="slice-1")
        self.assertEqual(len(unconsumed), 1)
        self.assertEqual(unconsumed[0]["text"], "Manter teto de 300 linhas")

        # 5. Configurações e Governança
        gov = store.get_governance_settings(pid)
        self.assertIn("security_preset", gov)
        updated_gov = store.update_governance_settings({"security_preset": "strict"}, project_id=pid)
        self.assertEqual(updated_gov["security_preset"], "strict")

        # 6. Human Gate
        gate_res = store.approve_gate("deploy_prod", approved_by="admin", project_id=pid)
        self.assertEqual(gate_res["status"], "APPROVED")
        status = store.get_gate_status("deploy_prod", project_id=pid)
        self.assertTrue(status["approved"])

    def test_06_builder_surgical_patch_and_scaffold_integrity(self):
        """(Critério 4b) Validação funcional de patching cirúrgico e garantia anti-arquivo vazio."""
        from tools.local_builder.surgical_patcher import apply_surgical_patch, resolve_safe_worktree_path
        from tools.local_builder.builder_service import generate_scaffold_fallback, is_file_empty_or_blank

        # 1. Criação direta de arquivo
        new_code, hunks, summary = apply_surgical_patch("", "def hello():\n    return 'world'\n")
        self.assertEqual(hunks, 1)
        self.assertIn("hello()", new_code)

        # 2. Patch SEARCH/REPLACE cirúrgico
        orig_code = "def calc(a, b):\n    return a - b\n"
        patch_text = "<<<<<<< SEARCH\n    return a - b\n=======\n    return a + b\n>>>>>>>"
        patched_code, hunks, summary = apply_surgical_patch(orig_code, patch_text)
        self.assertEqual(hunks, 1)
        self.assertIn("return a + b", patched_code)

        # 3. Scaffold fallback para HTML
        scaffold_html = generate_scaffold_fallback("index.html", "Crie #hero e #cards")
        self.assertIn("<!DOCTYPE html>", scaffold_html)
        self.assertIn('id="hero"', scaffold_html)

        # 4. Anti-empty check
        test_file = os.path.join(self.temp_dir, "blank.txt")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("   \n\n// apenas comentario\n")
        self.assertTrue(is_file_empty_or_blank(test_file))


if __name__ == "__main__":
    unittest.main()
