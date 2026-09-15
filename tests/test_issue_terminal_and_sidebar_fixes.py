import unittest
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_JS_PATH = os.path.join(BASE_DIR, "web", "app.js")
STYLES_CSS_PATH = os.path.join(BASE_DIR, "web", "styles.css")

class TestTerminalAndSidebarFixes(unittest.TestCase):
    def setUp(self):
        with open(APP_JS_PATH, "r", encoding="utf-8") as f:
            self.js = f.read()
        with open(STYLES_CSS_PATH, "r", encoding="utf-8") as f:
            self.css = f.read()

    def test_terminal_tabsbar_defensive_lookup_in_create_session(self):
        """Valida que createSession busca tabsBar e gridContainer defensivamente caso ainda não inicializados."""
        self.assertIn("this.tabsBar = document.getElementById('terminal-tabs-bar')", self.js)
        self.assertIn("this.gridContainer = document.getElementById('terminal-workspace-grid')", self.js)

    def test_terminal_init_called_on_app_startup(self):
        """Valida que terminalWorkspace.init() é chamado na inicialização da aplicação."""
        self.assertIn("terminalWorkspace.init()", self.js)

    def test_styles_css_does_not_hide_higher_index_terminals(self):
        """Valida que o CSS não oculta terminais a partir do 3º ou 5º filho com nth-child(n+5)."""
        self.assertNotIn(".terminal-pane:nth-child(n+5)", self.css)
        self.assertNotIn(".terminal-pane:nth-child(n+3)", self.css)

    def test_pinned_projects_does_not_auto_pin_current_project(self):
        """Valida que selecionar um projeto não o torna automaticamente pinned."""
        self.assertNotIn("pinnedProjects.push(fallback)", self.js)
        self.assertNotIn("return currentProjectId ? [currentProjectId] : ['default']", self.js)

    def test_projects_list_does_not_render_slices_nodes(self):
        """Valida que a lista de projetos na sidebar não renderiza nós de fatias verticais (SLICE-X)."""
        # A seção Projects (cardsList) não deve iterar sobre state.nodes adicionando cards de fatia
        self.assertNotIn("nodes.forEach(node => {", self.js)

if __name__ == "__main__":
    unittest.main()
