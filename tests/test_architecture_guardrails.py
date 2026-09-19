import os
import sys
import unittest
import tempfile
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Tentativa de importação da ferramenta de guardrails
try:
    from scripts.check_architecture_guardrails import (
        count_file_metrics,
        validate_architecture_guardrails,
        BASELINE_ALLOWLIST,
        PACKAGE_RULES,
        GLOBAL_KISS_THRESHOLD,
    )
except ImportError:
    count_file_metrics = None
    validate_architecture_guardrails = None
    BASELINE_ALLOWLIST = None
    PACKAGE_RULES = None
    GLOBAL_KISS_THRESHOLD = 400


class TestArchitectureGuardrails(unittest.TestCase):
    """Suíte de Governança e Arquitetura - Issue #36: Guardrails de Limite de Linhas (KISS Threshold)."""

    def setUp(self):
        if validate_architecture_guardrails is None:
            self.fail("scripts.check_architecture_guardrails não foi carregado corretamente.")

    def test_01_self_protection_unregistered_oversized_file_fails(self):
        """Autoproteção: Arquivo com > 400 linhas fora da allowlist deve falhar a validação."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "bloated_service.py")
            with open(test_file, "w", encoding="utf-8") as f:
                for i in range(401):
                    f.write(f"# Linha {i+1} de código\nx = {i}\n")
            
            violations = validate_architecture_guardrails(
                target_paths=[test_file],
                base_dir=tmpdir,
                allowlist={},
                global_max=GLOBAL_KISS_THRESHOLD,
            )
            self.assertTrue(len(violations) > 0, "Deveria registrar violação para arquivo > 400 linhas fora da allowlist.")
            self.assertTrue(any("bloated_service.py" in v.file_path for v in violations))
            self.assertTrue(any("400" in v.message or "teto" in v.message.lower() for v in violations))

    def test_02_self_protection_allowlist_growth_fails(self):
        """Autoproteção: Arquivo na allowlist que ultrapassa seu teto congelado deve falhar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "legacy_module.py")
            with open(test_file, "w", encoding="utf-8") as f:
                for i in range(501):
                    f.write(f"val_{i} = {i}\n")
            
            rel_path = "legacy_module.py"
            allowlist = {rel_path: 500}  # Teto congelado em 500
            
            violations = validate_architecture_guardrails(
                target_paths=[test_file],
                base_dir=tmpdir,
                allowlist=allowlist,
                global_max=GLOBAL_KISS_THRESHOLD,
            )
            self.assertTrue(len(violations) > 0, "Deveria registrar violação para arquivo legado que cresceu além do teto congelado.")
            self.assertTrue(any("congelado" in v.message.lower() or "allowlist" in v.message.lower() for v in violations))

    def test_03_legacy_allowlist_frozen_ceilings_not_exceeded(self):
        """Critério 2: Arquivos legados na BASELINE_ALLOWLIST não podem exceder seus tetos congelados."""
        self.assertIsNotNone(BASELINE_ALLOWLIST, "BASELINE_ALLOWLIST deve ser definida.")
        expected_legacy_files = [
            "web/js/terminal_workspace.js",
            "server/opencode_manager.py",
            "web/js/local_worker.js",
            "web/js/slices_chat.js",
            "server/mcp_server.py",
            "web/js/codebase_graph.js",
            "web/js/sidebar.js",
            "server/pty_manager.py",
            "server/code_graph.py",
            "web/js/file_explorer.js",
            "server/customizations_manager.py",
            "server/workers/worker_queue.py",
        ]
        for rel_path in expected_legacy_files:
            self.assertIn(rel_path, BASELINE_ALLOWLIST, f"{rel_path} deve estar na BASELINE_ALLOWLIST")
            full_path = os.path.join(BASE_DIR, rel_path)
            self.assertTrue(os.path.exists(full_path), f"Arquivo legado {rel_path} deve existir.")
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                actual_lines = sum(1 for _ in f)
            ceiling = BASELINE_ALLOWLIST[rel_path]
            self.assertLessEqual(
                actual_lines,
                ceiling,
                f"Arquivo legado {rel_path} cresceu! Linhas atuais: {actual_lines}, Teto congelado: {ceiling}"
            )

    def test_04_global_kiss_threshold_400_lines_in_codebase(self):
        """Critério 3: Bloquear novos arquivos no repositório (server/**/*.py e web/js/**/*.js) que excedam 400 linhas."""
        violations = validate_architecture_guardrails(
            base_dir=BASE_DIR,
            allowlist=BASELINE_ALLOWLIST,
            package_rules=PACKAGE_RULES,
            global_max=GLOBAL_KISS_THRESHOLD,
        )
        msg = "\n".join(str(v) for v in violations)
        self.assertEqual(len(violations), 0, f"Violações arquiteturais encontradas no repositório:\n{msg}")

    def test_05_package_specific_guardrails_issues_31_to_35(self):
        """Critério 4: Todos os arquivos refatorados nas issues #31-#35 devem respeitar rigorosamente seus tetos."""
        # 1. server/chat/ <= 250 linhas
        chat_dir = os.path.join(BASE_DIR, "server", "chat")
        for root, _, files in os.walk(chat_dir):
            for file in files:
                if file.endswith(".py"):
                    p = os.path.join(root, file)
                    with open(p, "r", encoding="utf-8") as f:
                        lines = sum(1 for _ in f)
                    rel = os.path.relpath(p, BASE_DIR)
                    self.assertLessEqual(lines, 250, f"{rel} excedeu 250 linhas (tem {lines})")

        # 2. server/routers/ <= 300 linhas
        routers_dir = os.path.join(BASE_DIR, "server", "routers")
        for root, _, files in os.walk(routers_dir):
            for file in files:
                if file.endswith(".py"):
                    p = os.path.join(root, file)
                    with open(p, "r", encoding="utf-8") as f:
                        lines = sum(1 for _ in f)
                    rel = os.path.relpath(p, BASE_DIR)
                    self.assertLessEqual(lines, 300, f"{rel} excedeu 300 linhas (tem {lines})")

        # 3. server/web_server.py < 200 linhas
        web_server_path = os.path.join(BASE_DIR, "server", "web_server.py")
        with open(web_server_path, "r", encoding="utf-8") as f:
            lines = sum(1 for _ in f)
        self.assertLess(lines, 200, f"server/web_server.py deve ter < 200 linhas (tem {lines})")

        # 4. server/storage/ <= 300 linhas
        storage_dir = os.path.join(BASE_DIR, "server", "storage")
        for root, _, files in os.walk(storage_dir):
            for file in files:
                if file.endswith(".py"):
                    p = os.path.join(root, file)
                    with open(p, "r", encoding="utf-8") as f:
                        lines = sum(1 for _ in f)
                    rel = os.path.relpath(p, BASE_DIR)
                    self.assertLessEqual(lines, 300, f"{rel} excedeu 300 linhas (tem {lines})")

        # 5. server/tools/local_builder/ <= 300 linhas
        lb_dir = os.path.join(BASE_DIR, "server", "tools", "local_builder")
        for root, _, files in os.walk(lb_dir):
            for file in files:
                if file.endswith(".py"):
                    p = os.path.join(root, file)
                    with open(p, "r", encoding="utf-8") as f:
                        lines = sum(1 for _ in f)
                    rel = os.path.relpath(p, BASE_DIR)
                    self.assertLessEqual(lines, 300, f"{rel} excedeu 300 linhas (tem {lines})")

        # 6. web/js/chat/ <= 250 linhas
        web_chat_dir = os.path.join(BASE_DIR, "web", "js", "chat")
        for root, _, files in os.walk(web_chat_dir):
            for file in files:
                if file.endswith(".js"):
                    p = os.path.join(root, file)
                    with open(p, "r", encoding="utf-8") as f:
                        lines = sum(1 for _ in f)
                    rel = os.path.relpath(p, BASE_DIR)
                    self.assertLessEqual(lines, 250, f"{rel} excedeu 250 linhas (tem {lines})")

        # 7. web/js/settings/ <= 350 linhas
        web_settings_dir = os.path.join(BASE_DIR, "web", "js", "settings")
        for root, _, files in os.walk(web_settings_dir):
            for file in files:
                if file.endswith(".js"):
                    p = os.path.join(root, file)
                    with open(p, "r", encoding="utf-8") as f:
                        lines = sum(1 for _ in f)
                    rel = os.path.relpath(p, BASE_DIR)
                    self.assertLessEqual(lines, 350, f"{rel} excedeu 350 linhas (tem {lines})")

    def test_06_sloc_metric_calculation(self):
        """Critério 1: Cálculo correto de métricas SLOC (código vs comentários vs linhas em branco)."""
        sample_code = (
            "# Cabeçalho de comentário\n"
            "\n"
            "def foo():\n"
            "    # Comentário interno\n"
            "    x = 10\n"
            "    return x\n"
            "\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(sample_code)
            tmp_path = f.name

        try:
            metrics = count_file_metrics(tmp_path)
            self.assertEqual(metrics.total_lines, 7)
            self.assertEqual(metrics.blank_lines, 2)
            self.assertEqual(metrics.comment_lines, 2)
            self.assertEqual(metrics.sloc, 3)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_07_cli_script_execution(self):
        """Critério 1: Script executável via terminal com status de sucesso no repositório."""
        script_path = os.path.join(BASE_DIR, "scripts", "check_architecture_guardrails.py")
        self.assertTrue(os.path.isfile(script_path), f"Script {script_path} deve existir.")
        res = subprocess.run(
            [sys.executable, script_path, "--summary"],
            capture_output=True,
            text=True,
            cwd=BASE_DIR
        )
        self.assertEqual(res.returncode, 0, f"Script falhou com stderr:\n{res.stderr}\nstdout:\n{res.stdout}")
        self.assertIn("GUARDRAILS DE ARQUITETURA", res.stdout.upper())


if __name__ == "__main__":
    unittest.main()
