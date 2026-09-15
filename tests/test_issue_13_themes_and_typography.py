import unittest
import os

class TestIssue13ThemesAndTypography(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html_path = os.path.join(base_dir, 'web', 'index.html')
        cls.css_path = os.path.join(base_dir, 'web', 'styles.css')
        cls.js_path = os.path.join(base_dir, 'web', 'js', 'settings.js')

        with open(cls.html_path, 'r', encoding='utf-8') as f:
            cls.html_content = f.read()

        with open(cls.css_path, 'r', encoding='utf-8') as f:
            cls.css_content = f.read()

        with open(cls.js_path, 'r', encoding='utf-8') as f:
            cls.js_content = f.read()

    def test_css_themes(self):
        """Valida se o CSS contém as paletas completas para os 4 temas."""
        css = self.css_content
        self.assertIn('[data-theme="dark"]', css)
        self.assertIn('[data-theme="light"]', css)
        self.assertIn('[data-theme="classic"]', css)
        self.assertIn('[data-theme="sepia"]', css)

    def test_font_scale_variable(self):
        """Valida presença da variável de escala de fonte."""
        css = self.css_content
        self.assertIn('--app-font-scale', css)

    def test_html_controls(self):
        """Valida seletores de tema e tamanho de fonte no HTML e remoção de neon bloom."""
        html = self.html_content
        self.assertIn('id="ag-theme-select"', html)
        self.assertIn('id="ag-font-size-select"', html)
        self.assertNotIn('Neon Glow & Bloom', html)

    def test_js_events(self):
        """Valida que settings.js escuta tema e escala de fonte."""
        js = self.js_content
        self.assertIn('ag_theme', js)
        self.assertIn('ag_font_scale', js)
        self.assertIn('initThemeAndFontSettings', js)

    def test_terminal_theme_variables_and_js_sync(self):
        """Valida se os terminais acompanham o tema via tokens CSS e JS reativo."""
        css = self.css_content
        self.assertIn('--terminal-bg:', css)
        self.assertIn('--terminal-fg:', css)
        self.assertIn('--terminal-cursor:', css)

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        term_js_path = os.path.join(base_dir, 'web', 'js', 'terminal_workspace.js')
        with open(term_js_path, 'r', encoding='utf-8') as f:
            term_js = f.read()

        self.assertIn('getTerminalTheme', term_js)
        self.assertIn("theme: this.getTerminalTheme()", term_js)
        self.assertIn("theme-changed", term_js)
        self.assertIn("minimumContrastRatio: 4.5", term_js)

        # Valida que .xterm-rows e .xterm possuem cor de texto semântica
        self.assertIn(".pane-body .xterm-rows", css)
        self.assertIn(".ollama-log-line .log-content", css)

if __name__ == '__main__':
    unittest.main()
