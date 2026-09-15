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

if __name__ == '__main__':
    unittest.main()
