import os
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR = os.path.join(BASE_DIR, "web")
JS_DIR = os.path.join(WEB_DIR, "js")
APP_JS_PATH = os.path.join(WEB_DIR, "app.js")
INDEX_HTML_PATH = os.path.join(WEB_DIR, "index.html")

class TestIssue9ModularRefactor(unittest.TestCase):
    """Testes para a Issue #9: Decomposição Modular do app.js (Clean Architecture & SOLID)."""

    def setUp(self):
        with open(APP_JS_PATH, "r", encoding="utf-8") as f:
            self.app_js = f.read()
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            self.index_html = f.read()

    def test_app_js_line_count_under_300(self):
        """Critério 1: app.js deve ter menos de 300 linhas como orquestrador enxuto."""
        lines = [l for l in self.app_js.splitlines() if l.strip()]
        self.assertLess(len(lines), 300, f"app.js possui {len(lines)} linhas não vazias, deve ser < 300")

    def test_all_ten_modules_exist(self):
        """Critério 2: Devem existir todos os 10 módulos especializados em web/js/."""
        expected_modules = [
            "ui_utils.js",
            "state.js",
            "sidebar.js",
            "terminal_workspace.js",
            "file_explorer.js",
            "slices_chat.js",
            "codebase_graph.js",
            "local_worker.js",
            "settings.js",
            "websocket_client.js"
        ]
        for mod in expected_modules:
            mod_path = os.path.join(JS_DIR, mod)
            self.assertTrue(os.path.isfile(mod_path), f"Módulo {mod} não encontrado em web/js/")
            with open(mod_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertGreater(len(content.strip()), 100, f"Módulo {mod} está vazio ou muito curto")

    def test_terminal_workspace_module(self):
        """Valida que terminal_workspace.js encapsula TerminalWorkspaceManager."""
        with open(os.path.join(JS_DIR, "terminal_workspace.js"), "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("class TerminalWorkspaceManager", js)
        self.assertIn("terminalWorkspace = new TerminalWorkspaceManager()", js)
        self.assertIn("initOrFitTerminal", js)
        self.assertIn("sendTerminalCommand", js)

    def test_file_explorer_module(self):
        """Valida que file_explorer.js encapsula FileExplorerManager."""
        with open(os.path.join(JS_DIR, "file_explorer.js"), "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("class FileExplorerManager", js)
        self.assertIn("fileExplorerManager = new FileExplorerManager()", js)

    def test_state_module(self):
        """Valida que state.js centraliza reatividade, persistência e indicadores semânticos."""
        with open(os.path.join(JS_DIR, "state.js"), "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("function switchProject", js)
        self.assertIn("function getProjectDotClass", js)
        self.assertIn("function getProjectDotTitle", js)
        self.assertIn("function getPinnedProjectIds", js)
        self.assertIn("function getRecentProjectIds", js)
        self.assertIn("function recordRecentProject", js)

    def test_sidebar_module(self):
        """Valida que sidebar.js governa workspaces e renderWorktreeSidebar."""
        with open(os.path.join(JS_DIR, "sidebar.js"), "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("function renderWorktreeSidebar", js)
        self.assertIn("function togglePinProject", js)
        self.assertIn("function toggleShowMoreProjects", js)
        self.assertIn("function switchTab", js)

    def test_local_worker_module(self):
        """Valida que local_worker.js encapsula o ciclo de vida do Ollama e console."""
        with open(os.path.join(JS_DIR, "local_worker.js"), "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("function startOllamaServer", js)
        self.assertIn("function stopOllamaServer", js)
        self.assertIn("function openOllamaConsole", js)
        self.assertIn("function renderOllamaLogLine", js)

    def test_websocket_client_module(self):
        """Valida que websocket_client.js encapsula a conexão WebSocket / SSE."""
        with open(os.path.join(JS_DIR, "websocket_client.js"), "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("function initWebSocket", js)
        self.assertIn("STATE_FULL", js)

    def test_html_loads_app_js_as_module(self):
        """Valida que index.html carrega app.js com type='module'."""
        self.assertIn('<script type="module" src="app.js', self.index_html)

    def test_app_js_exports_window_globals(self):
        """Valida que app.js expõe APIs essenciais no escopo window para eventos do DOM."""
        self.assertIn("Object.assign(window,", self.app_js)
        self.assertIn("switchProject", self.app_js)
        self.assertIn("terminalWorkspace", self.app_js)
        self.assertIn("fileExplorerManager", self.app_js)

if __name__ == "__main__":
    unittest.main()
