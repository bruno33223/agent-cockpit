import os
import sys
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Adiciona o diretório server ao path
SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from state_store import db
from tools.local_builder_tool import (
    execute_local_builder,
    manage_local_model,
    apply_surgical_patch,
    resolve_safe_worktree_path,
)

class TestLocalBuilder(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="cockpit_test_")
        self.slice_id = "slice-test"
        # Configura worktree falso para testes de isolamento
        self.worktree_dir = os.path.join(self.test_dir, ".worktrees", self.slice_id)
        os.makedirs(self.worktree_dir, exist_ok=True)
        # Reseta contador de tentativas e garante delegate_styles_to_cloud desativado nos testes base
        db.set_local_worker_config({"delegate_styles_to_cloud": False})
        if hasattr(db, "reset_local_worker_attempts"):
            db.reset_local_worker_attempts(self.slice_id)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    # 1. Testes de StateStore para local_worker config e contagem de tentativas
    def test_state_store_local_worker_config(self):
        cfg = db.get_local_worker_config()
        self.assertIn("provider", cfg)
        self.assertIn("endpoint", cfg)
        self.assertIn("model", cfg)
        self.assertEqual(cfg["circuit_breaker_threshold"], 2)

        # Atualização de config
        updated = db.set_local_worker_config({"model": "custom-model:latest"})
        self.assertEqual(updated.get("model"), "custom-model:latest")
        self.assertEqual(db.get_local_worker_config().get("model"), "custom-model:latest")

    def test_state_store_circuit_breaker_attempts(self):
        self.assertEqual(db.get_local_worker_attempts(self.slice_id), 0)
        c1 = db.increment_local_worker_attempts(self.slice_id)
        self.assertEqual(c1, 1)
        self.assertEqual(db.get_local_worker_attempts(self.slice_id), 1)

        c2 = db.increment_local_worker_attempts(self.slice_id)
        self.assertEqual(c2, 2)
        self.assertEqual(db.get_local_worker_attempts(self.slice_id), 2)

        db.reset_local_worker_attempts(self.slice_id)
        self.assertEqual(db.get_local_worker_attempts(self.slice_id), 0)

    # 2. Testes de resolução segura de caminho e patch_engine
    def test_resolve_safe_worktree_path(self):
        # Caminho válido dentro da worktree
        target_abs = resolve_safe_worktree_path(self.slice_id, "src/calculator.py", repo_root=self.test_dir)
        expected = os.path.abspath(os.path.join(self.worktree_dir, "src/calculator.py"))
        self.assertEqual(target_abs, expected)

        # Tentativas de directory traversal devem falhar com ValueError
        with self.assertRaises(ValueError):
            resolve_safe_worktree_path(self.slice_id, "../outside.py", repo_root=self.test_dir)

        with self.assertRaises(ValueError):
            resolve_safe_worktree_path(self.slice_id, "/etc/passwd", repo_root=self.test_dir)

        with self.assertRaises(ValueError):
            resolve_safe_worktree_path(self.slice_id, "foo/../../outside.py", repo_root=self.test_dir)

    def test_apply_surgical_patch_exact_match(self):
        original = "def add(a, b):\n    return a - b\n"
        patch_block = "<<<<<<< SEARCH\n    return a - b\n=======\n    return a + b\n>>>>>>>"
        new_content, hunks, diff_summary = apply_surgical_patch(original, patch_block)
        self.assertEqual(hunks, 1)
        self.assertIn("+1 -1", diff_summary)
        self.assertEqual(new_content, "def add(a, b):\n    return a + b\n")

    def test_apply_surgical_patch_direct_new_file(self):
        # Arquivo novo recebendo código em markdown fence diretamente
        original = ""
        patch_block = "```html\n<!DOCTYPE html>\n<html><body><h1>Olá Mundo</h1></body></html>\n```"
        new_content, hunks, diff_summary = apply_surgical_patch(original, patch_block)
        self.assertEqual(hunks, 1)
        self.assertIn("+2 -0 lines", diff_summary)
        self.assertIn("<h1>Olá Mundo</h1>", new_content)

    def test_apply_surgical_patch_whole_file_update(self):
        # Arquivo pequeno atualizado completamente sem marcadores SEARCH/REPLACE
        original = "/* CSS */\nbody { background: #000; }\n"
        patch_block = "```css\n/* CSS */\nbody { background: #090d16; }\n.btn { color: cyan; }\n```"
        new_content, hunks, diff_summary = apply_surgical_patch(original, patch_block)
        self.assertEqual(hunks, 1)
        self.assertIn("whole-file update", diff_summary)
        self.assertIn(".btn { color: cyan; }", new_content)

    def test_apply_surgical_patch_atomic_failure(self):
        original = "def hello():\n    print('world')\n"
        # SEARCH que não existe no arquivo
        bad_patch = "<<<<<<< SEARCH\n    return 42\n=======\n    return 100\n>>>>>>>"
        with self.assertRaises(ValueError):
            apply_surgical_patch(original, bad_patch)

    # 3. Testes de execute_local_builder (Zero-Fluff JSON e Circuit Breaker)
    @patch("tools.local_builder_tool.call_local_llm")
    def test_execute_local_builder_zero_fluff_contract(self, mock_llm):
        # Mock do LLM local retornando bloco SEARCH/REPLACE
        mock_llm.return_value = {
            "patch": "<<<<<<< SEARCH\ndef subtract(a, b):\n    return a - b\n=======\ndef add(a, b):\n    return a + b\n>>>>>>>",
            "tokens": 45,
            "duration_ms": 120
        }

        # Cria arquivo alvo na worktree
        target_rel = "src/calc.py"
        target_abs = os.path.join(self.worktree_dir, target_rel)
        os.makedirs(os.path.dirname(target_abs), exist_ok=True)
        with open(target_abs, "w", encoding="utf-8") as f:
            f.write("def subtract(a, b):\n    return a - b\n")

        res = execute_local_builder(
            slice_id=self.slice_id,
            instruction="Corrija a função para somar em vez de subtrair",
            target_file=target_rel,
            repo_root=self.test_dir
        )

        # Valida formato Zero-Fluff JSON
        self.assertEqual(res.get("status"), "DELIVERED")
        self.assertEqual(res.get("slice_id"), self.slice_id)
        self.assertEqual(res.get("target_file"), target_rel)
        self.assertGreaterEqual(res.get("hunks_applied", 0), 1)
        self.assertIn("+", res.get("diff_summary", ""))
        self.assertIn("-", res.get("diff_summary", ""))
        self.assertIn("execution_time_ms", res)
        self.assertEqual(res.get("local_tokens_generated"), 45)

        # Valida que o arquivo foi modificado no disco
        with open(target_abs, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("def add(a, b):", content)
        self.assertIn("return a + b", content)

    def test_execute_local_builder_circuit_breaker(self):
        # Configura duas tentativas consecutivas já falhas
        db.increment_local_worker_attempts(self.slice_id)
        db.increment_local_worker_attempts(self.slice_id)
        self.assertEqual(db.get_local_worker_attempts(self.slice_id), 2)

        res = execute_local_builder(
            slice_id=self.slice_id,
            instruction="Tentativa excedente que deve acionar circuit breaker",
            target_file="src/foo.py",
            repo_root=self.test_dir,
            error_feedback="Test failure: AssertionError"
        )

        # Deve retornar ESCALATION_REQUIRED sem executar LLM local
        self.assertEqual(res.get("status"), "ESCALATION_REQUIRED")
        self.assertEqual(res.get("slice_id"), self.slice_id)
        self.assertEqual(res.get("reason"), "local_worker_threshold_exceeded")
        self.assertIn("last_error", res)

    # 4. Testes de manage_local_model (status, list, select, pull)
    @patch("urllib.request.urlopen")
    def test_manage_local_model_actions(self, mock_urlopen):
        # 4.1. Status
        res_status = manage_local_model(action="status")
        self.assertIn("status", res_status)
        self.assertIn("current_model", res_status)
        self.assertIn("endpoint", res_status)

        # 4.2. List
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "models": [{"name": "qwen2.5-coder:7b-instruct-q4_k_m"}, {"name": "deepseek-coder:6.7b"}]
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        res_list = manage_local_model(action="list")
        self.assertIn("models", res_list)

        # 4.3. Select
        res_sel = manage_local_model(action="select", model_name="deepseek-coder:6.7b")
        self.assertEqual(res_sel.get("status"), "SELECTED")
        self.assertEqual(res_sel.get("model"), "deepseek-coder:6.7b")
        self.assertEqual(db.get_local_worker_config().get("model"), "deepseek-coder:6.7b")

        # 4.4. Pull
        mock_pull_resp = MagicMock()
        mock_pull_resp.read.return_value = json.dumps({"status": "success"}).encode("utf-8")
        mock_pull_resp.__enter__.return_value = mock_pull_resp
        mock_urlopen.return_value = mock_pull_resp

        res_pull = manage_local_model(action="pull", model_name="qwen2.5-coder:7b")
        self.assertIn(res_pull.get("status"), ["PULLED", "SUCCESS", "PULL_STARTED"])
        self.assertEqual(res_pull.get("model"), "qwen2.5-coder:7b")

    # 5. Testes da Garantia Anti-Arquivo Vazio (Mock Fallback) e Fila
    @patch("tools.local_builder_tool.call_local_llm")
    def test_mock_fallback_on_empty_or_failed_llm(self, mock_llm):
        """Garante que quando o LLM local falha ou não entrega nada, o arquivo NUNCA fica vazio."""
        mock_llm.side_effect = RuntimeError("Ollama connection refused")

        target_file = "public/index.html"
        res = execute_local_builder(
            slice_id=self.slice_id,
            instruction="Crie a landing page com #hero e #pricing",
            target_file=target_file,
            repo_root=self.test_dir
        )

        self.assertEqual(res.get("status"), "DELIVERED")
        target_abs = os.path.join(self.worktree_dir, target_file)
        self.assertTrue(os.path.exists(target_abs))
        with open(target_abs, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertGreater(len(content.strip()), 50)
        self.assertIn("<!DOCTYPE html>", content)
        self.assertIn("id=\"hero\"", content)
        self.assertIn("id=\"pricing\"", content)

    @patch("tools.local_builder_tool.call_local_llm")
    def test_mock_fallback_css_js_python(self, mock_llm):
        """Valida fallback para arquivos .css, .js e .py."""
        mock_llm.side_effect = RuntimeError("GPU out of memory")

        # CSS
        res_css = execute_local_builder(
            slice_id=self.slice_id,
            instruction="Estilo dark com variáveis",
            target_file="src/styles.css",
            repo_root=self.test_dir
        )
        self.assertEqual(res_css.get("status"), "DELIVERED")
        with open(os.path.join(self.worktree_dir, "src/styles.css"), "r", encoding="utf-8") as f:
            css_content = f.read()
        self.assertIn(":root", css_content)
        self.assertIn("--bg-primary", css_content)

        # JS
        res_js = execute_local_builder(
            slice_id=self.slice_id,
            instruction="Inicialização da aplicação",
            target_file="src/app.js",
            repo_root=self.test_dir
        )
        self.assertEqual(res_js.get("status"), "DELIVERED")
        with open(os.path.join(self.worktree_dir, "src/app.js"), "r", encoding="utf-8") as f:
            js_content = f.read()
        self.assertIn("DOMContentLoaded", js_content)

        # PY
        res_py = execute_local_builder(
            slice_id=self.slice_id,
            instruction="Módulo da calculadora de impostos",
            target_file="src/tax_calculator.py",
            repo_root=self.test_dir
        )
        self.assertEqual(res_py.get("status"), "DELIVERED")
        with open(os.path.join(self.worktree_dir, "src/tax_calculator.py"), "r", encoding="utf-8") as f:
            py_content = f.read()
        self.assertIn("class TaxCalculator", py_content)
        self.assertIn("unittest", py_content)

    def test_get_worker_queue_status_tool(self):
        """Verifica a MCP tool get_worker_queue_status."""
        from tools.local_builder_tool import get_worker_queue_status
        q_status = get_worker_queue_status(slice_id="slice-test")
        self.assertIn("is_busy", q_status)
        self.assertIn("queue_length", q_status)
        self.assertIn("message", q_status)


if __name__ == "__main__":
    unittest.main()

