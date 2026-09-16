import os
import sys
import json
import time
import socket
import threading
import unittest
import urllib.request
import urllib.error
import uvicorn

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from code_graph import get_file_vault_note, save_file_vault_note
from git_worktrees import create_slice_worktree, cleanup_slice_worktree
from web_server import app


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class TestIssue19PathTraversal(unittest.TestCase):
    server_thread = None
    server = None
    port = None
    base_url = None

    @classmethod
    def setUpClass(cls):
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        config = uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="error")
        cls.server = uvicorn.Server(config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()

        started = False
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"{cls.base_url}/api/health", timeout=1.0) as resp:
                    if resp.getcode() == 200:
                        started = True
                        break
            except Exception:
                time.sleep(0.1)

        if not started:
            raise RuntimeError("Não foi possível iniciar o servidor uvicorn para testes de segurança.")

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.should_exit = True

    # -------------------------------------------------------------------------
    # 1. Code Graph: Vault Notes Direct Function Tests
    # -------------------------------------------------------------------------
    def test_code_graph_vault_note_get_path_traversal(self):
        with self.assertRaises(ValueError):
            get_file_vault_note("/tmp", "../../etc/passwd")

        with self.assertRaises(ValueError):
            get_file_vault_note("/tmp", "../something_outside")

    def test_code_graph_vault_note_save_path_traversal(self):
        with self.assertRaises(ValueError):
            save_file_vault_note("/tmp", "../../etc/shadow", "malicious content")

        with self.assertRaises(ValueError):
            save_file_vault_note("/tmp", "../escape", "malicious content")

    # -------------------------------------------------------------------------
    # 2. Git Worktrees: slice_id Validation Tests
    # -------------------------------------------------------------------------
    def test_git_worktrees_create_invalid_slice_ids(self):
        invalid_slices = [
            "../../etc",
            "/tmp/malicious",
            "..",
            "slice/subpath",
            "slice\\subpath",
            "slice 1",
            "slice;rm -rf",
            "slice$name",
        ]
        for bad_id in invalid_slices:
            with self.subTest(slice_id=bad_id):
                with self.assertRaises(ValueError):
                    create_slice_worktree(slice_id=bad_id, repo_root="/tmp")

    def test_git_worktrees_cleanup_invalid_slice_ids(self):
        invalid_slices = [
            "../../etc",
            "/tmp/malicious",
            "..",
            "slice/subpath",
            "slice\\subpath",
            "slice*danger",
        ]
        for bad_id in invalid_slices:
            with self.subTest(slice_id=bad_id):
                with self.assertRaises(ValueError):
                    cleanup_slice_worktree(slice_id=bad_id, repo_root="/tmp")

    # -------------------------------------------------------------------------
    # 3. Web Server: HTTP API Path Traversal & 403 Forbidden Tests
    # -------------------------------------------------------------------------
    def test_api_vault_note_get_traversal_returns_403(self):
        url = f"{self.base_url}/api/vault/note?file=../../etc/passwd"
        req = urllib.request.Request(url)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_api_vault_note_post_traversal_returns_403(self):
        url = f"{self.base_url}/api/vault/note"
        payload = json.dumps({"file": "../../etc/shadow", "content": "pwned"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_api_terminal_session_invalid_slice_id_returns_403(self):
        url = f"{self.base_url}/api/terminal/sessions"
        payload = json.dumps({
            "slice_id": "../../etc",
            "role": "orchestrator"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_api_terminal_session_path_traversal_cwd_returns_403(self):
        url = f"{self.base_url}/api/terminal/sessions"
        payload = json.dumps({
            "slice_id": "slice-valid",
            "cwd": "../../../../../etc"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
