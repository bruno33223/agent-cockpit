import unittest
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_JS_PATH = os.path.join(BASE_DIR, "web", "app.js")
TERMINAL_JS_PATH = os.path.join(BASE_DIR, "web", "js", "terminal_workspace.js")
SIDEBAR_JS_PATH = os.path.join(BASE_DIR, "web", "js", "sidebar.js")
FILE_EXPLORER_JS_PATH = os.path.join(BASE_DIR, "web", "js", "file_explorer.js")
INDEX_HTML_PATH = os.path.join(BASE_DIR, "web", "index.html")
STYLES_CSS_PATH = os.path.join(BASE_DIR, "web", "styles.css")

class TestIssue10TerminalWorkspaceUX(unittest.TestCase):
    def setUp(self):
        with open(TERMINAL_JS_PATH, "r", encoding="utf-8") as f:
            self.term_js = f.read()
        with open(SIDEBAR_JS_PATH, "r", encoding="utf-8") as f:
            self.sidebar_js = f.read()
        with open(FILE_EXPLORER_JS_PATH, "r", encoding="utf-8") as f:
            self.explorer_js = f.read()
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            self.html = f.read()
        with open(STYLES_CSS_PATH, "r", encoding="utf-8") as f:
            self.css = f.read()

    def test_terminal_removed_hardcoded_fable_and_tabs(self):
        """Valida remoção do texto hardcoded Fable e da poluição visual das abas de terminais."""
        self.assertNotIn("Fable 5 1M", self.term_js)
        self.assertNotIn("1 PTYs |", self.term_js)
        # O subtítulo com Fable 5 1M e statusline ruidosa devem ser removidos
        self.assertNotIn("orca-pane-subtitle", self.term_js)
        self.assertNotIn("orca-terminal-statusline", self.term_js)

    def test_terminal_header_only_close_button(self):
        """Valida que o cabeçalho do terminal mantém apenas o botão fechar (×), removendo split, clear e restart."""
        self.assertIn("orca-btn-close", self.term_js)
        self.assertNotIn("orca-btn-split", self.term_js)
        self.assertNotIn("orca-btn-clear", self.term_js)
        self.assertNotIn("orca-btn-restart", self.term_js)

    def test_grid_config_and_zoom_controls(self):
        """Valida presença do menu Configurar Grid e dos controles de Zoom In/Out."""
        self.assertIn("btn-config-grid", self.html)
        self.assertIn("btn-zoom-in-term", self.html)
        self.assertIn("btn-zoom-out-term", self.html)
        # No JS deve haver suporte a zoom e pan na área de trabalho
        self.assertIn("zoomLevel", self.term_js)
        self.assertIn("setZoom", self.term_js)
        self.assertIn("setLayoutMode", self.term_js)

    def test_orchestrator_subagents_button(self):
        """Valida que o orquestrador possui botão para acessar subagentes e não título com coroa."""
        self.assertNotIn("👑 Orquestrador Staff", self.term_js)
        self.assertIn("btn-orchestrator-subagents", self.term_js)

    def test_about_modal_structure(self):
        """Valida a existência do modal Sobre o ZEUS AGENT com ícone expandido, versão e criador Bruno."""
        self.assertIn("modal-about-zeus", self.html)
        self.assertIn("zeus-brand", self.html)
        self.assertIn("Bruno", self.html)
        self.assertIn("openAboutModal", self.sidebar_js)

    def test_sidebar_toggle_and_right_sidebar_reopen(self):
        """Valida que o hambúrguer oculta a left sidebar e a right sidebar tem botão de reexibição persistente."""
        # Right sidebar deve ter botão de reabertura sempre acessível
        self.assertIn("btn-reopen-right-sidebar", self.html)
        self.assertIn("btn-reopen-right-sidebar", self.explorer_js)
        # Left sidebar deve ter classe para ocultação completa
        self.assertIn("sidebar-pinned-hidden", self.css)

if __name__ == "__main__":
    unittest.main()
