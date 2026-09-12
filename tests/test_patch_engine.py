import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Garantir que o workspace está no path de importação
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from server.workers.patch_engine import PatchEngine, PatchBlock, PatchResult
from server.workers.local_llm_client import LocalLLMClient


class TestPatchEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.engine = PatchEngine(workspace_root=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_blocks_single(self):
        patch_text = """<<<<<<< SEARCH
def old_function():
    return 1
=======
def new_function():
    return 2
>>>>>>>"""
        blocks = self.engine.parse_blocks(patch_text)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].search.strip(), "def old_function():\n    return 1")
        self.assertEqual(blocks[0].replace.strip(), "def new_function():\n    return 2")

    def test_parse_blocks_multiple(self):
        patch_text = """Algum texto explicativo antes...
<<<<<<< SEARCH
x = 10
=======
x = 20
>>>>>>>
Texto intermediário...
<<<<<<< SEARCH
y = "hello"
=======
y = "world"
>>>>>>>
"""
        blocks = self.engine.parse_blocks(patch_text)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].search.strip(), "x = 10")
        self.assertEqual(blocks[0].replace.strip(), "x = 20")
        self.assertEqual(blocks[1].search.strip(), 'y = "hello"')
        self.assertEqual(blocks[1].replace.strip(), 'y = "world"')

    def test_parse_blocks_empty_search(self):
        patch_text = """<<<<<<< SEARCH
=======
# Arquivo novo
print("Hello World")
>>>>>>>"""
        blocks = self.engine.parse_blocks(patch_text)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].search, "")
        self.assertIn('print("Hello World")', blocks[0].replace)

    def test_parse_blocks_malformed(self):
        # Bloco sem fechamento deve gerar ValueError
        malformed = """<<<<<<< SEARCH
def incomplete():
    pass
=======
"""
        with self.assertRaises(ValueError):
            self.engine.parse_blocks(malformed)

    def test_validate_path_valid(self):
        valid_path = self.engine.validate_path("src/module.py")
        expected = Path(self.temp_dir) / "src" / "module.py"
        self.assertEqual(valid_path.resolve(), expected.resolve())

    def test_validate_path_traversal_rejection(self):
        with self.assertRaises(ValueError):
            self.engine.validate_path("../../etc/passwd")

        with self.assertRaises(ValueError):
            self.engine.validate_path("/etc/shadow")

    def test_apply_patch_single_match(self):
        file_path = Path(self.temp_dir) / "target.py"
        file_path.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")

        patch_text = """<<<<<<< SEARCH
b = 2
=======
b = 42
>>>>>>>"""
        result = self.engine.apply_patch(file_path="target.py", patch_content=patch_text)
        self.assertTrue(result.success)
        self.assertEqual(file_path.read_text(encoding="utf-8"), "a = 1\nb = 42\nc = 3\n")
        self.assertIn("-b = 2", result.diff)
        self.assertIn("+b = 42", result.diff)
        self.assertEqual(result.additions, 1)
        self.assertEqual(result.deletions, 1)

    def test_apply_patch_ambiguous_match_rollback(self):
        file_path = Path(self.temp_dir) / "ambiguous.py"
        initial_content = "item = 1\nitem = 1\n"
        file_path.write_text(initial_content, encoding="utf-8")

        patch_text = """<<<<<<< SEARCH
item = 1
=======
item = 99
>>>>>>>"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.apply_patch(file_path="ambiguous.py", patch_content=patch_text)

        self.assertIn("ambíguo", str(ctx.exception).lower())
        # Garante que o arquivo original está intacto (rollback)
        self.assertEqual(file_path.read_text(encoding="utf-8"), initial_content)

    def test_apply_patch_not_found_match_rollback(self):
        file_path = Path(self.temp_dir) / "not_found.py"
        initial_content = "line1\nline2\n"
        file_path.write_text(initial_content, encoding="utf-8")

        patch_text = """<<<<<<< SEARCH
line_missing
=======
line_replaced
>>>>>>>"""
        with self.assertRaises(ValueError) as ctx:
            self.engine.apply_patch(file_path="not_found.py", patch_content=patch_text)

        self.assertIn("não encontrado", str(ctx.exception).lower())
        self.assertEqual(file_path.read_text(encoding="utf-8"), initial_content)

    def test_apply_patch_multi_block_atomic_rollback(self):
        file_path = Path(self.temp_dir) / "atomic.py"
        initial_content = "first = True\nsecond = False\n"
        file_path.write_text(initial_content, encoding="utf-8")

        # Primeiro bloco é válido, segundo bloco falha -> rollback total
        patch_text = """<<<<<<< SEARCH
first = True
=======
first = False
>>>>>>>
<<<<<<< SEARCH
inexistent = True
=======
inexistent = False
>>>>>>>"""
        with self.assertRaises(ValueError):
            self.engine.apply_patch(file_path="atomic.py", patch_content=patch_text)

        # first = True NÃO pode ter sido alterado
        self.assertEqual(file_path.read_text(encoding="utf-8"), initial_content)

    def test_apply_patch_create_new_file(self):
        patch_text = """<<<<<<< SEARCH
=======
def created_file():
    return "ok"
>>>>>>>"""
        result = self.engine.apply_patch(file_path="new_sub/created.py", patch_content=patch_text)
        self.assertTrue(result.success)
        created_file = Path(self.temp_dir) / "new_sub" / "created.py"
        self.assertTrue(created_file.exists())
        self.assertIn('def created_file():', created_file.read_text(encoding="utf-8"))
        self.assertGreater(result.additions, 0)
        self.assertEqual(result.deletions, 0)

    def test_apply_patch_diff_summary(self):
        file_path = Path(self.temp_dir) / "calc.py"
        file_path.write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")

        patch_text = """<<<<<<< SEARCH
y = 2
z = 3
=======
y = 20
z = 30
w = 40
>>>>>>>"""
        result = self.engine.apply_patch(file_path="calc.py", patch_content=patch_text)
        self.assertTrue(result.success)
        self.assertEqual(result.deletions, 2)
        self.assertEqual(result.additions, 3)
        self.assertIn("-y = 2", result.diff)
        self.assertIn("+w = 40", result.diff)


class TestLocalLLMClient(unittest.TestCase):
    def setUp(self):
        self.client = LocalLLMClient(base_url="http://127.0.0.1:11434", timeout=2.0)

    @patch("urllib.request.urlopen")
    def test_healthcheck_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertTrue(self.client.healthcheck())

    @patch("urllib.request.urlopen")
    def test_healthcheck_failure(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        self.assertFalse(self.client.healthcheck())

    @patch("urllib.request.urlopen")
    def test_list_models_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.read.return_value = b'{"models": [{"name": "qwen2.5-coder:7b"}, {"name": "llama3.2:3b"}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        models = self.client.list_models()
        self.assertIn("installed", models)
        self.assertIn("recommended", models)
        self.assertIn("qwen2.5-coder:7b", models["installed"])
        self.assertTrue(len(models["recommended"]) > 0)

    @patch("urllib.request.urlopen")
    def test_list_models_fallback_when_offline(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        models = self.client.list_models()
        self.assertEqual(models["installed"], [])
        self.assertTrue(len(models["recommended"]) > 0)
        self.assertFalse(models.get("online", True))

    @patch("urllib.request.urlopen")
    def test_pull_model(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.read.return_value = b'{"status": "success"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = self.client.pull_model("qwen2.5-coder:7b")
        self.assertEqual(result.get("status"), "success")

    @patch("urllib.request.urlopen")
    def test_pull_model_streaming(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.__iter__.return_value = [
            b'{"status": "pulling manifest"}\n',
            b'{"status": "downloading", "completed": 500, "total": 1000}\n',
            b'{"status": "success"}\n'
        ]
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        progress_chunks = []
        result = self.client.pull_model(
            "qwen2.5-coder:7b",
            stream=True,
            progress_callback=progress_chunks.append
        )
        self.assertEqual(result.get("status"), "success")
        self.assertEqual(len(progress_chunks), 3)
        self.assertEqual(progress_chunks[1].get("completed"), 500)


    def test_format_patch_prompt(self):
        prompt = self.client.format_patch_prompt(
            file_path="server/app.py",
            file_content="def main():\n    pass\n",
            instructions="Adicione log de inicialização"
        )
        self.assertIn("server/app.py", prompt)
        self.assertIn("Adicione log de inicialização", prompt)
        self.assertIn("<<<<<<< SEARCH", prompt)
        self.assertIn("=======", prompt)
        self.assertIn(">>>>>>>", prompt)

    @patch("urllib.request.urlopen")
    def test_chat_completion(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.read.return_value = b'{"choices": [{"message": {"role": "assistant", "content": "<<<<<<< SEARCH\\npass\\n=======\\nprint(1)\\n>>>>>>>"}}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        response = self.client.chat_completion(
            messages=[{"role": "user", "content": "hello"}],
            model="qwen2.5-coder:7b"
        )
        self.assertIn("choices", response)
        self.assertEqual(response["choices"][0]["message"]["content"], "<<<<<<< SEARCH\npass\n=======\nprint(1)\n>>>>>>>")


if __name__ == "__main__":
    unittest.main()
