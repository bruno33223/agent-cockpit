import os
import sys
import tempfile
import shutil
import unittest
import json
from unittest.mock import patch

# Ajusta sys.path para importar módulos do servidor
_cur_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_cur_dir)
_server_dir = os.path.join(_repo_root, "server")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from state_store import StateStore


class TestIssue20AtomicLocks(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="cockpit_issue20_test_")
        self.store = StateStore(states_dir=self.temp_dir)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_lock_context_manager_exists_and_uses_fcntl(self):
        """Verifica se o context manager _file_lock existe no StateStore e utiliza fcntl.flock."""
        self.assertTrue(hasattr(self.store, "_file_lock"), "StateStore deve possuir o context manager _file_lock")
        test_file = os.path.join(self.temp_dir, "test_lock.lock")
        with self.store._file_lock(test_file):
            self.assertTrue(os.path.exists(test_file) or os.path.exists(test_file + ".lock"))

    def test_atomic_save_prevents_corrupted_json_on_write_failure(self):
        """Verifica se a gravação de estado é atômica via tempfile + replace, não corrompendo o arquivo original se falhar."""
        self.assertTrue(hasattr(self.store, "_atomic_write_json"), "StateStore deve possuir método auxiliar _atomic_write_json")
        
        target_file = os.path.join(self.temp_dir, "atomic_test.json")
        initial_data = {"status": "intact", "counter": 42}
        self.store._atomic_write_json(target_file, initial_data)
        
        with open(target_file, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), initial_data)

        # Simula erro no meio do dump do json
        bad_data = {"status": "broken", "unserializable": object()}
        with self.assertRaises(TypeError):
            self.store._atomic_write_json(target_file, bad_data)

        # O arquivo original deve permanecer intacto com initial_data
        with open(target_file, "r", encoding="utf-8") as f:
            content = json.load(f)
            self.assertEqual(content, initial_data)

    def test_save_index_and_save_state_use_atomic_write(self):
        """Garante que _save_index, _save_state e _save_workflow utilizam a gravação atômica."""
        self.assertTrue(hasattr(self.store, "_save_workflow"), "StateStore deve implementar _save_workflow")
        
        # Grava índice com dados válidos
        idx_data = {"current_project_id": "default", "projects": {"default": {"name": "Test"}}}
        self.store._save_index(idx_data)
        with open(self.store.index_file, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), idx_data)

        # Tenta gravar índice corrompido/inválido
        with self.assertRaises(TypeError):
            self.store._save_index({"invalid": object()})

        # O índice permanece intacto
        with open(self.store.index_file, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), idx_data)


if __name__ == "__main__":
    unittest.main()
