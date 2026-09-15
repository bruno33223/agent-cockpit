import unittest
import os
import re

class TestIssue11UiRedesignMinimalist(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html_path = os.path.join(base_dir, 'web', 'index.html')
        cls.css_path = os.path.join(base_dir, 'web', 'styles.css')

        assert os.path.exists(cls.html_path), f"Arquivo index.html não encontrado em {cls.html_path}"
        assert os.path.exists(cls.css_path), f"Arquivo styles.css não encontrado em {cls.css_path}"

        with open(cls.html_path, 'r', encoding='utf-8') as f:
            cls.html_content = f.read()

        with open(cls.css_path, 'r', encoding='utf-8') as f:
            cls.css_content = f.read()

    def test_minimalist_topbar_structure(self):
        """Valida que o topo possui estrutura minimalista e limpa, sem tags/cabeçalhos pesados obsoletos."""
        html = self.html_content
        self.assertTrue('class="orca-titlebar titlebar topbar"' in html or 'class="topbar' in html)
        self.assertIn('id="orca-titlebar"', html)

    def test_hairline_divider_and_flat_brand(self):
        """Valida linha divisória sutil e marca minimalista sem borda pesada de neon."""
        css = self.css_content
        self.assertIn('.topbar-divider', css)
        self.assertIn('border-bottom: 1px solid var(--border-subtle)', css)

if __name__ == '__main__':
    unittest.main()
