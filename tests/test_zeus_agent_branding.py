import os
import unittest
import xml.etree.ElementTree as ET

class TestZeusAgentBranding(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.html_path = os.path.join(self.base_dir, 'web', 'index.html')
        self.css_path = os.path.join(self.base_dir, 'web', 'styles.css')
        self.svg_path = os.path.join(self.base_dir, 'web', 'zeus_terminal_god.svg')

        with open(self.html_path, 'r', encoding='utf-8') as f:
            self.html_content = f.read()
        with open(self.css_path, 'r', encoding='utf-8') as f:
            self.css_content = f.read()

    def test_zeus_standalone_svg_file_exists_and_valid(self):
        """Valida que o arquivo vetorial do Deus Olímpico Zeus existe e é um XML SVG válido."""
        self.assertTrue(os.path.exists(self.svg_path), "Arquivo zeus_terminal_god.svg deve existir em web/")
        with open(self.svg_path, 'r', encoding='utf-8') as f:
            svg_content = f.read()
        
        self.assertIn('id="zeusTerminalSvg"', svg_content)
        self.assertIn('ZEUS AGENT - Terminal Bash God Icon', svg_content)
        self.assertIn('zeus@agent:~# ./godmode --daemon', svg_content)
        self.assertIn('[ ZEUS_AGENT_CLI ]', svg_content)

        # Validação de parse XML
        tree = ET.fromstring(svg_content)
        self.assertEqual(tree.tag.split('}')[-1], 'svg')

    def test_index_html_title_and_favicon(self):
        """Valida que o título e o favicon utilizam a identidade ZEUS AGENT."""
        self.assertIn('<title>ZEUS AGENT - Telemetria & Orquestração Multiagente</title>', self.html_content)
        self.assertIn('href="zeus_terminal_god.svg"', self.html_content)

    def test_index_html_titlebar_brand_zeus(self):
        """Valida que a marca principal na titlebar foi atualizada de Orca para ZEUS AGENT com o ícone do Deus Olímpico."""
        self.assertIn('class="orca-brand"', self.html_content)
        self.assertIn('title="ZEUS AGENT"', self.html_content)
        self.assertIn('ZEUS AGENT', self.html_content)
        self.assertIn('id="zeus-brand-logo"', self.html_content)
        self.assertIn('aria-label="ZEUS AGENT - Deus Olímpico"', self.html_content)
        # Não deve haver a baleia Orca
        self.assertNotIn('🐋', self.html_content)

    def test_index_html_workbench_header_zeus(self):
        """Valida que o cabeçalho do terminal workbench utiliza o nome predominante ZEUS AGENT."""
        self.assertIn('ZEUS AGENT Multi-Pane Workbench & Terminal', self.html_content)
        self.assertIn('zeus-workbench-emblem', self.html_content)

    def test_styles_css_zeus_brand_rules(self):
        """Valida as regras de estilo de ZEUS AGENT e do emblema olímpico em styles.css."""
        self.assertIn('.orca-brand', self.css_content)
        self.assertIn('.orca-brand-title', self.css_content)
        self.assertIn('.zeus-workbench-emblem-wrap', self.css_content)

if __name__ == '__main__':
    unittest.main()
