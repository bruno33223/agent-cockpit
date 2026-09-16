import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

# Importa local_builder_tool (compatível tanto via tools quanto workers)
try:
    from workers.local_builder_tool import apply_surgical_patch, call_local_llm
except ImportError:
    from tools.local_builder_tool import apply_surgical_patch, call_local_llm

try:
    from workers.ollama_client import OllamaClient, calculate_dynamic_num_ctx
except ImportError:
    OllamaClient = None
    calculate_dynamic_num_ctx = None


class TestSurgicalPatchAlignment(unittest.TestCase):
    """Testa que apply_surgical_patch não corrompe caracteres nem sofre index mismatch."""

    def test_apply_surgical_patch_with_trailing_whitespace_before_target(self):
        """
        Garante que quando há linhas com trailing whitespace ANTES do bloco SEARCH,
        o índice da substituição não seja deslocado assimetricamente corrompendo o arquivo.
        """
        original = (
            "def header():   \n"  # 3 espaços no final
            "    pass        \n"  # 8 espaços no final
            "\n"
            "def target_function():\n"
            "    return 'old_value'\n"
            "\n"
            "def footer():\n"
            "    return True\n"
        )

        patch_block = (
            "<<<<<<< SEARCH\n"
            "def target_function():\n"
            "    return 'old_value'\n"
            "=======\n"
            "def target_function():\n"
            "    return 'new_value'\n"
            ">>>>>>>\n"
        )

        new_content, hunks, summary = apply_surgical_patch(original, patch_block)
        self.assertEqual(hunks, 1)

        # O cabeçalho deve permanecer intacto, com seus espaços originais
        self.assertTrue(new_content.startswith("def header():   \n    pass        \n"))
        # O rodapé deve permanecer intacto
        self.assertTrue(new_content.endswith("def footer():\n    return True\n"))
        # O alvo deve ter sido alterado corretamente
        self.assertIn("def target_function():\n    return 'new_value'\n", new_content)
        self.assertNotIn("'old_value'", new_content)

    def test_apply_surgical_patch_tabs_and_indentation(self):
        """
        Garante alinhamento exato quando o arquivo possui tabulações e indentação profunda.
        """
        original = (
            "\tclass Service:\n"
            "\t\tdef run(self):\n"
            "\t\t\tstep_1()\n"
            "\t\t\tstep_2()\n"
            "\t\t\treturn 'done'\n"
        )

        patch_block = (
            "<<<<<<< SEARCH\n"
            "\t\t\tstep_2()\n"
            "=======\n"
            "\t\t\tstep_2_modified()\n"
            ">>>>>>>\n"
        )

        new_content, hunks, summary = apply_surgical_patch(original, patch_block)
        self.assertEqual(hunks, 1)
        expected = (
            "\tclass Service:\n"
            "\t\tdef run(self):\n"
            "\t\t\tstep_1()\n"
            "\t\t\tstep_2_modified()\n"
            "\t\t\treturn 'done'\n"
        )
        self.assertEqual(new_content, expected)

    def test_apply_surgical_patch_search_with_trailing_whitespace_mismatch(self):
        """
        Se o bloco SEARCH omitir trailing whitespace que existe no arquivo original,
        o patch deve ser aplicado sem descolamento das linhas adjacentes.
        """
        original = (
            "# Top comment   \n"  # 3 espaços
            "x = 10   \n"          # 3 espaços
            "y = 20\n"
        )

        # Bloco SEARCH sem os espaços extras
        patch_block = (
            "<<<<<<< SEARCH\n"
            "x = 10\n"
            "=======\n"
            "x = 99\n"
            ">>>>>>>\n"
        )

        new_content, hunks, summary = apply_surgical_patch(original, patch_block)
        self.assertEqual(hunks, 1)
        # Deve preservar # Top comment   com seus espaços e substituir x = 10
        self.assertTrue(new_content.startswith("# Top comment   \n"))
        self.assertIn("x = 99", new_content)
        self.assertNotIn("x = 10", new_content)
        self.assertTrue(new_content.endswith("y = 20\n"))


class TestOllamaClientContextWindow(unittest.TestCase):
    """Testa num_ctx ampliado para 8192 por padrão, suporte a customização e dimensionamento dinâmico."""

    def test_ollama_client_module_exists(self):
        """Verifica se o módulo server.workers.ollama_client existe e foi importado."""
        self.assertIsNotNone(OllamaClient, "OllamaClient deve existir em server/workers/ollama_client.py")

    def test_ollama_client_default_num_ctx(self):
        """OllamaClient deve usar 8192 como context window padrão (evitando truncamento de 2048)."""
        client = OllamaClient()
        self.assertEqual(client.default_num_ctx, 8192)

    def test_ollama_client_generate_payload_options(self):
        """Ao chamar generate, o payload deve conter num_ctx=8192 por padrão."""
        client = OllamaClient()
        with patch.object(client, "_request", return_value={"response": "ok", "done": True}) as mock_req:
            client.generate(prompt="hello world", model="qwen2.5-coder:7b")
            self.assertTrue(mock_req.called)
            endpoint = mock_req.call_args[0][0]
            payload = mock_req.call_args[1].get("payload", {})
            self.assertEqual(endpoint, "/api/generate")
            options = payload.get("options", {})
            self.assertEqual(options.get("num_ctx"), 8192)

    def test_ollama_client_custom_num_ctx_preserved(self):
        """Permite que o chamador passe num_ctx customizado via options sem ser sobrescrito."""
        client = OllamaClient()
        with patch.object(client, "_request", return_value={"response": "ok", "done": True}) as mock_req:
            client.generate(
                prompt="hello world",
                model="qwen2.5-coder:7b",
                options={"num_ctx": 16384, "temperature": 0.2}
            )
            payload = mock_req.call_args[1].get("payload", {})
            options = payload.get("options", {})
            self.assertEqual(options.get("num_ctx"), 16384)
            self.assertEqual(options.get("temperature"), 0.2)

    def test_dynamic_num_ctx_calculation(self):
        """calculate_dynamic_num_ctx dimensiona com base no tamanho do prompt e arquivo."""
        # Prompt pequeno: retorna o mínimo padrão de 8192
        small_prompt = "Instrução curta de 50 caracteres."
        ctx_small = calculate_dynamic_num_ctx(small_prompt, min_ctx=8192)
        self.assertEqual(ctx_small, 8192)

        # Prompt gigante com 30.000 caracteres (~7500 tokens) + buffer de saída
        huge_prompt = "x = 1\n" * 6000  # 36.000 caracteres
        ctx_huge = calculate_dynamic_num_ctx(huge_prompt, min_ctx=8192, max_ctx=32768)
        self.assertGreater(ctx_huge, 8192)
        self.assertLessEqual(ctx_huge, 32768)

    def test_local_builder_call_local_llm_uses_8192_default(self):
        """call_local_llm em local_builder_tool.py deve utilizar 8192 por padrão ao invés de 2048."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"response": "patch", "eval_count": 10}).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            call_local_llm(
                instruction="teste",
                target_file="test.py",
                existing_content="print('hello')",
                config={}
            )

            req = mock_urlopen.call_args[0][0]
            body = json.loads(req.data.decode("utf-8"))
            options = body.get("options", {})
            self.assertEqual(
                options.get("num_ctx"),
                8192,
                "call_local_llm deve enviar num_ctx=8192 por padrão para evitar truncamento silencioso"
            )


if __name__ == "__main__":
    unittest.main()
