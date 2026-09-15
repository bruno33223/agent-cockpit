import os
import sys
import unittest
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

class TestIssue5TerminalMinimalistSplit(unittest.TestCase):
    def setUp(self):
        self.html_path = os.path.join(BASE_DIR, "web", "index.html")
        self.css_path = os.path.join(BASE_DIR, "web", "styles.css")
        self.js_path = os.path.join(BASE_DIR, "web", "app.js")

        with open(self.html_path, "r", encoding="utf-8") as f:
            self.html_content = f.read()
        with open(self.css_path, "r", encoding="utf-8") as f:
            self.css_content = f.read()
        with open(self.js_path, "r", encoding="utf-8") as f:
            self.js_content = f.read()

    def test_minimalist_header_and_single_primary_new_terminal_button(self):
        """Critério 1 e 2: Zero cabeçalhos ou textos descritivos no topo dos terminais, mantendo botão '+ Novo Terminal'."""
        self.assertIn('id="btn-new-terminal"', self.html_content)
        self.assertIn('+ Novo Terminal', self.html_content)
        # O cabeçalho visível do workbench não deve expor o parágrafo longo explicativo
        # Deve ter classe .minimalist ou ter sido limpo para foco exclusivo nos terminais
        self.assertIn('terminal-workbench-minimalist', self.html_content + self.css_content)

    def test_ultraminimal_spacing_gap_in_css(self):
        """Critério 4: Margens e paddings reduzidos ao mínimo (gap sutil de 2px a 4px)."""
        self.assertIn('.terminal-workspace-grid', self.css_content)
        # Verifica se há regras de split dinâmico com gap <= 4px
        self.assertTrue(
            bool(re.search(r'gap:\s*[234]px', self.css_content)),
            "Deveria haver gap de 2px a 4px para o grid de terminais"
        )

    def test_dynamic_split_in_app_js(self):
        """Critério 3 e 5: Divisão dinâmica em split ao adicionar novos terminais e redistribuição automática ao fechar."""
        # Deve haver lógica de split dinâmico automático (ex: applyDynamicSplit ou split automático por contagem)
        self.assertTrue(
            'applyDynamicSplit' in self.js_content or 'layout-dynamic' in self.js_content or 'updateDynamicSplit' in self.js_content,
            "app.js deve conter lógica de split dinâmico automático"
        )
        # Deve invocar fitAll para ajuste fluido do XTerm
        self.assertIn('this.fitAll()', self.js_content)

    def test_compatibility_with_existing_test_suite(self):
        """Garante que a suíte de testes legados (branding e workbench) continue satisfeita."""
        self.assertIn('ZEUS AGENT Multi-Pane Workbench & Terminal', self.html_content)
        self.assertIn('zeus-workbench-emblem', self.html_content)
        self.assertIn('terminal-layout-picker', self.html_content)
        self.assertIn('data-layout="tabs"', self.html_content)
        self.assertIn('data-layout="split"', self.html_content)
        self.assertIn('data-layout="grid"', self.html_content)

if __name__ == '__main__':
    unittest.main()
