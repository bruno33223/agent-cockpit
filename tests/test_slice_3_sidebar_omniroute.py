import unittest
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SIDEBAR_JS = os.path.join(BASE_DIR, "web", "js", "sidebar.js")
STYLES_CSS = os.path.join(BASE_DIR, "web", "styles.css")
CSS_STYLES_CSS = os.path.join(BASE_DIR, "web", "css", "styles.css")

class TestSlice3SidebarOmniroute(unittest.TestCase):
    def setUp(self):
        with open(SIDEBAR_JS, "r", encoding="utf-8") as f:
            self.sidebar_js = f.read()
        with open(STYLES_CSS, "r", encoding="utf-8") as f:
            self.styles_css = f.read()

    def test_sidebar_omniroute_click_simulation_removed(self):
        """Valida que a simulação de clique defeituosa foi eliminada."""
        self.assertNotIn("origTest.click()", self.sidebar_js)
        self.assertNotIn("document.getElementById('btn-test-omniroute').click()", self.sidebar_js)

    def test_sidebar_omniroute_direct_api_fetch(self):
        """Valida que o botão #btn-ag-test-omniroute chama diretamente apiFetch('/api/omniroute/status')."""
        self.assertIn("apiFetch(`/api/omniroute/status", self.sidebar_js)
        self.assertIn("ag-omniroute-feedback", self.sidebar_js)

    def test_sidebar_omniroute_button_resets_in_finally(self):
        """Valida que o botão é desbloqueado no bloco finally sem travar em Testando..."""
        self.assertIn("btnTestOmni.disabled = false;", self.sidebar_js)
        self.assertIn("btnTestOmni.textContent = originalText;", self.sidebar_js)

    def test_sidebar_omniroute_latency_and_models_feedback(self):
        """Valida renderização de latência e modelos detectados na mensagem de feedback."""
        self.assertIn("performance.now()", self.sidebar_js)
        self.assertIn("ag-feedback-msg success", self.sidebar_js)
        self.assertIn("ag-feedback-msg error", self.sidebar_js)

    def test_omniroute_styles_present(self):
        """Valida que os estilos refinados para conectores, badges e feedback estão no CSS."""
        self.assertIn(".ag-feedback-msg.success", self.styles_css)
        self.assertIn(".ag-feedback-msg.error", self.styles_css)
        self.assertIn(".ag-feedback-msg.testing", self.styles_css)
        self.assertIn(".omniroute-connector-container", self.styles_css)
        self.assertIn(".omniroute-badge", self.styles_css)

    def test_web_css_styles_css_compatibility(self):
        """Valida que web/css/styles.css existe e resolve os mesmos estilos."""
        self.assertTrue(os.path.exists(CSS_STYLES_CSS))
        with open(CSS_STYLES_CSS, "r", encoding="utf-8") as f:
            css_content = f.read()
        self.assertIn(".omniroute-badge", css_content)

if __name__ == "__main__":
    unittest.main()
