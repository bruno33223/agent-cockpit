import unittest
import os
import sys
import json
from fastapi import HTTPException

# Insere a raiz do repositório no path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
SERVER_DIR = os.path.join(BASE_DIR, 'server')
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from server.web_server import get_fs_tree, read_fs_file, app

class TestFileExplorerSidebar(unittest.TestCase):
    def setUp(self):
        self.base_dir = BASE_DIR
        self.html_path = os.path.join(self.base_dir, 'web', 'index.html')
        self.js_path = os.path.join(self.base_dir, 'web', 'app.js')
        self.css_path = os.path.join(self.base_dir, 'web', 'styles.css')

        with open(self.html_path, 'r', encoding='utf-8') as f:
            self.html_content = f.read()
        with open(self.js_path, 'r', encoding='utf-8') as f:
            self.js_content = f.read()
        with open(self.css_path, 'r', encoding='utf-8') as f:
            self.css_content = f.read()

    # 1. TESTES DE BACKEND (/api/fs/tree & /api/fs/read)
    def test_backend_fs_tree_root(self):
        tree = get_fs_tree()
        self.assertIsInstance(tree, dict)
        self.assertIn("root", tree)
        self.assertIn("name", tree)
        self.assertIn("project_id", tree)
        self.assertIn("entries", tree)
        self.assertTrue(os.path.exists(tree["root"]))
        self.assertGreater(len(tree["entries"]), 0)

        entry_names = [e["name"] for e in tree["entries"]]
        self.assertNotIn(".git", entry_names)
        self.assertNotIn("__pycache__", entry_names)
        self.assertIn("requirements.txt", entry_names)

    def test_backend_fs_tree_subpath(self):
        tree_server = get_fs_tree(subpath="server")
        self.assertEqual(tree_server["subpath"], "server")
        server_entries = [e["name"] for e in tree_server["entries"]]
        self.assertIn("web_server.py", server_entries)
        self.assertIn("state_store.py", server_entries)

    def test_backend_fs_tree_security_traversal(self):
        with self.assertRaises(HTTPException) as ctx:
            get_fs_tree(subpath="../../etc")
        self.assertIn(ctx.exception.status_code, [403, 404])

    def test_backend_fs_read_file(self):
        data = read_fs_file(path="requirements.txt")
        self.assertIsInstance(data, dict)
        self.assertEqual(data["name"], "requirements.txt")
        self.assertFalse(data["is_binary"])
        self.assertIn("fastapi", data["content"])
        self.assertGreater(data["size"], 0)

    def test_backend_fs_read_security_traversal(self):
        with self.assertRaises(HTTPException) as ctx:
            read_fs_file(path="../../../../etc/passwd")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_backend_fs_read_not_found(self):
        with self.assertRaises(HTTPException) as ctx:
            read_fs_file(path="non_existing_file_12345.xyz")
        self.assertEqual(ctx.exception.status_code, 404)

    # 2. TESTES DE ESTRUTURA HTML (Orca Right Sidebar)
    def test_html_right_sidebar_structure(self):
        self.assertIn('class="workspace-sidebar"', self.html_content)
        self.assertIn('id="orca-right-sidebar"', self.html_content)
        self.assertIn('id="right-sidebar-project-name"', self.html_content)
        self.assertIn('id="btn-refresh-right-sidebar"', self.html_content)
        self.assertIn('id="btn-collapse-right-sidebar"', self.html_content)

    def test_html_right_sidebar_tabs(self):
        self.assertIn('class="right-sidebar-tabs"', self.html_content)
        self.assertIn('id="tab-right-files"', self.html_content)
        self.assertIn('id="tab-right-fleet"', self.html_content)
        self.assertIn('id="tab-right-steering"', self.html_content)

    def test_html_right_sidebar_panels(self):
        self.assertIn('right-panel-files', self.html_content)
        self.assertIn('right-panel-fleet', self.html_content)
        self.assertIn('right-panel-steering', self.html_content)

        self.assertIn('id="file-explorer-container"', self.html_content)
        self.assertIn('id="file-filter-input"', self.html_content)
        self.assertIn('id="file-preview-drawer"', self.html_content)
        self.assertIn('id="btn-copy-file-path"', self.html_content)

        self.assertIn('id="pairs-container"', self.html_content)
        self.assertIn('id="chat-messages"', self.html_content)
        self.assertIn('id="chat-form"', self.html_content)
        self.assertIn('id="chat-input"', self.html_content)

    # 3. TESTES DE LÓGICA JAVASCRIPT (app.js)
    def test_js_file_explorer_manager_class(self):
        self.assertIn('class FileExplorerManager', self.js_content)
        self.assertIn('loadFileTree(projectId', self.js_content)
        self.assertIn('renderTree()', self.js_content)
        self.assertIn('filterEntries(', self.js_content)
        self.assertIn('createTreeNodeElement(', self.js_content)
        self.assertIn('toggleDirectory(', self.js_content)
        self.assertIn('selectAndOpenFile(', self.js_content)
        self.assertIn('getFileIconInfo(', self.js_content)
        self.assertIn('switchRightTab(', self.js_content)

    def test_js_sync_on_project_switch(self):
        self.assertIn('fileExplorerManager.loadFileTree(currentProjectId)', self.js_content)
        self.assertIn('fileExplorerManager.init()', self.js_content)
        self.assertIn('PROJECT_ROOT_UPDATED', self.js_content)

    # 4. TESTES DE ESTILOS CSS (styles.css)
    def test_css_orca_right_sidebar_rules(self):
        self.assertIn('.right-sidebar-header', self.css_content)
        self.assertIn('.right-sidebar-project-name', self.css_content)
        self.assertIn('.right-sidebar-tabs', self.css_content)
        self.assertIn('.right-sidebar-tab', self.css_content)
        self.assertIn('.right-sidebar-tab.active', self.css_content)
        self.assertIn('.right-sidebar-panel', self.css_content)
        self.assertIn('.file-explorer-toolbar', self.css_content)
        self.assertIn('.file-filter-input', self.css_content)
        self.assertIn('.file-explorer-container', self.css_content)
        self.assertIn('.tree-node', self.css_content)
        self.assertIn('.tree-row', self.css_content)
        self.assertIn('.tree-toggle', self.css_content)
        self.assertIn('.file-preview-drawer', self.css_content)

if __name__ == '__main__':
    unittest.main()
