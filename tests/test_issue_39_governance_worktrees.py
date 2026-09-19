import os
import sys
import json
import shutil
import tempfile
import subprocess
import unittest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import workflow_lock
from storage.project_cleaner import default_initial_state, verify_commit_proof, detect_base_branch
from storage.state_facade import StateFacade


class TestIssue39GovernanceAndWorktrees(unittest.TestCase):
    """
    Testes de aceitação para Issue #39:
    1. Governança Humana Real em workflow_lock e default_initial_state (gate_plan_approved=False por padrão).
    2. Resolução dinâmica de branch base (detect_base_branch: origin/HEAD, main, master, branch atual, HEAD).
    3. Suporte a base_branch=None e auto-recuperação em verify_commit_proof.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cockpit_issue39_")
        self.states_dir = os.path.join(self.temp_dir, "states")
        os.makedirs(self.states_dir, exist_ok=True)
        self.facade = StateFacade(states_dir=self.states_dir)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _init_git_repo(self, path: str, branch: str = "main") -> str:
        """Helper para criar um repositório git com branch inicial configurada."""
        os.makedirs(path, exist_ok=True)
        subprocess.run(["git", "init", "-b", branch], cwd=path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Cockpit Tester"], cwd=path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "tester@cockpit.local"], cwd=path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", f"Initial commit on {branch}"], cwd=path, check=True, capture_output=True)
        return path

    # --- Item a: Criação de lock com gate_plan_approved: False ---
    def test_a_create_blueprint_lock_initializes_gates_unapproved(self):
        """Valida que create_blueprint_lock inicializa human_gates com gate_plan_approved: False e gate_ship_approved: False."""
        bp_dir = os.path.join(self.temp_dir, "bp_01")
        slices = [
            {"id": "slice-1", "title": "Contratos", "acceptance_criteria": "Critério 1"},
            {"id": "slice-2", "title": "Regras", "acceptance_criteria": "Critério 2"},
        ]
        lock_path = workflow_lock.create_blueprint_lock(
            blueprint_dir=bp_dir,
            epic_name="Épico Teste",
            goal="Validar gates humanos não aprovados por padrão",
            slices=slices,
        )
        self.assertTrue(os.path.exists(lock_path))

        with open(lock_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        gates = data.get("human_gates", {})
        self.assertFalse(gates.get("gate_plan_approved"), "gate_plan_approved deve iniciar como False por padrão")
        self.assertFalse(gates.get("gate_ship_approved"), "gate_ship_approved deve iniciar como False por padrão")

    # --- Item b: Estado inicial com gate_plan_approved: False ---
    def test_b_default_initial_state_initializes_gate_plan_approved_false(self):
        """Valida que default_initial_state inicializa human_gates com gate_plan_approved: False."""
        state = default_initial_state("Projeto Teste", self.temp_dir)
        gates = state.get("human_gates", {})

        self.assertFalse(gates.get("gate_plan_approved"), "gate_plan_approved deve ser False no default_initial_state")
        self.assertFalse(gates.get("gate_ship_approved"), "gate_ship_approved deve ser False no default_initial_state")
        self.assertIsNone(gates.get("last_approved_at"))
        self.assertIsNone(gates.get("approved_by"))

    # --- Item c: Aprovação formal do gate via approve_gate ---
    def test_c_approve_gate_formal_approval(self):
        """Valida a aprovação formal do gate_plan_approved via approve_gate e registro de timestamp/aprovador."""
        # 1. Teste via StateFacade / SettingsRepository
        initial_status = self.facade.get_gate_status("gate_plan_approved")
        self.assertFalse(initial_status.get("approved"))

        res = self.facade.approve_gate("gate_plan_approved", approved_by="human_lead")
        self.assertEqual(res.get("status"), "APPROVED")
        self.assertEqual(res.get("gate"), "gate_plan_approved")
        self.assertEqual(res.get("approved_by"), "human_lead")

        updated_status = self.facade.get_gate_status("gate_plan_approved")
        self.assertTrue(updated_status.get("approved"))
        self.assertEqual(updated_status.get("approved_by"), "human_lead")
        self.assertIsNotNone(updated_status.get("last_approved_at"))

        # 2. Teste de aprovação em blueprint.lock.json se existir helper em workflow_lock
        bp_dir = os.path.join(self.temp_dir, "bp_02")
        workflow_lock.create_blueprint_lock(
            blueprint_dir=bp_dir,
            epic_name="Épico Lock",
            goal="Aprovação no lock",
            slices=[{"id": "slice-1", "title": "S1"}],
        )
        if hasattr(workflow_lock, "approve_gate"):
            lock_res = workflow_lock.approve_gate("gate_plan_approved", approved_by="human_lead", blueprint_dir=bp_dir)
            self.assertEqual(lock_res.get("status"), "APPROVED")
            lock_file = os.path.join(bp_dir, "blueprint.lock.json")
            with open(lock_file, "r", encoding="utf-8") as f:
                lock_data = json.load(f)
            self.assertTrue(lock_data["human_gates"]["gate_plan_approved"])
            self.assertEqual(lock_data["human_gates"]["approved_by"], "human_lead")

    # --- Item d: Detecção dinâmica de branch base ---
    def test_d_detect_base_branch(self):
        """Valida a detecção dinâmica de branch base em diferentes cenários de repositórios git."""
        # Cenário 1: Repositório com branch 'main'
        repo_main = os.path.join(self.temp_dir, "repo_main")
        self._init_git_repo(repo_main, branch="main")
        self.assertEqual(detect_base_branch(repo_main), "main")

        # Cenário 2: Repositório com branch 'master'
        repo_master = os.path.join(self.temp_dir, "repo_master")
        self._init_git_repo(repo_master, branch="master")
        self.assertEqual(detect_base_branch(repo_master), "master")

        # Cenário 3: Repositório com branch personalizada sem main nem master (ex: 'develop')
        repo_develop = os.path.join(self.temp_dir, "repo_develop")
        self._init_git_repo(repo_develop, branch="develop")
        self.assertEqual(detect_base_branch(repo_develop), "develop")

        # Cenário 4: Repositório com remote origin simbólico (refs/remotes/origin/HEAD)
        repo_remote = os.path.join(self.temp_dir, "repo_remote")
        self._init_git_repo(repo_remote, branch="main")
        # Simula criação de refs/remotes/origin/HEAD apontando para refs/remotes/origin/custom_trunk
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/custom_trunk", "HEAD"],
            cwd=repo_remote, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/custom_trunk"],
            cwd=repo_remote, check=True, capture_output=True
        )
        self.assertEqual(detect_base_branch(repo_remote), "custom_trunk")

    # --- Item e: Verificação de commits com base_branch dinâmica ---
    def test_e_verify_commit_proof_dynamic_base_branch(self):
        """Valida que verify_commit_proof funciona com base_branch=None em repo com 'main' e sem 'master'."""
        repo_dir = os.path.join(self.temp_dir, "repo_slice_main")
        self._init_git_repo(repo_dir, branch="main")

        # Garante que 'master' não existe
        res_chk = subprocess.run(["git", "rev-parse", "--verify", "master"], cwd=repo_dir, capture_output=True, text=True)
        self.assertNotEqual(res_chk.returncode, 0, "A branch master não deve existir neste teste")

        # Cria a branch cockpit/slice-test a partir de main
        slice_branch = "cockpit/slice-test"
        subprocess.run(["git", "checkout", "-b", slice_branch], cwd=repo_dir, check=True, capture_output=True)

        # 1. Sem commits adicionais -> deve falhar porque aponta para a base
        res_no_commit = verify_commit_proof(repo_dir, "slice-test", base_branch=None)
        self.assertFalse(res_no_commit.get("valid_proof"))
        self.assertIn("Nenhum commit de trabalho foi produzido", res_no_commit.get("reason", ""))

        # 2. Faz um commit de trabalho na branch do slice
        test_file = os.path.join(repo_dir, "feature.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("# Feature implementada pelo subagente\n")
        subprocess.run(["git", "add", "feature.py"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat: slice implementation completed"], cwd=repo_dir, check=True, capture_output=True)

        # 3. Com base_branch=None -> detecta 'main' e valida prova
        res_proof = verify_commit_proof(repo_dir, "slice-test", base_branch=None)
        self.assertTrue(res_proof.get("valid_proof"), f"Falha na prova: {res_proof}")
        self.assertEqual(res_proof.get("commits_count"), 1)
        self.assertIn("feat: slice implementation completed", res_proof.get("latest_commit_msg", ""))

        # 4. Com base_branch='master' explícito (legado) em repo que só tem 'main' -> auto-recupera via detecção
        res_fallback = verify_commit_proof(repo_dir, "slice-test", base_branch="master")
        self.assertTrue(res_fallback.get("valid_proof"), f"Deveria auto-recuperar para main quando master não existe: {res_fallback}")

        # 5. Validação via Facade e ProjectRepository
        facade_proof = self.facade.verify_worktree_commit_proof(repo_dir, "slice-test")
        self.assertTrue(facade_proof.get("valid_proof"))
        self.assertEqual(facade_proof.get("commits_count"), 1)


if __name__ == "__main__":
    unittest.main()
