import unittest
import os
import re

class TestLandingStyles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css_path = 'landing-page/styles.css'
        assert os.path.exists(cls.css_path), "landing-page/styles.css não existe"
        with open(cls.css_path, 'r', encoding='utf-8') as f:
            cls.content = f.read()

    def test_landing_page_styles(self):
        content = self.content
        # Verifica se contém variáveis :root (--bg-primary, --cyan-neon, --purple-neon)
        self.assertIn('--bg-primary', content)
        self.assertIn('--cyan-neon', content)
        self.assertIn('--purple-neon', content)

        # Verifica se seções semânticas com suas classes obrigatórias existem
        classes = [
            '.site-header', '.brand', '.badge-version', '.nav-menu',
            '.hero-section', '.hero-badge', '.pulse-glow', '.hero-title',
            '.text-gradient-cyan', '.hero-subtitle', '.hero-cta-group',
            '.stats-grid', '.stat-card', '.stat-num', '.stat-label',
            '.architecture-section', '.fleet-grid', '.agent-pair-card',
            '.pair-header', '.pair-badge', '.builder-box', '.critic-box',
            '.status-pill', '.simulator-section', '.terminal-window',
            '.terminal-topbar', '.window-dots', '.terminal-title',
            '.terminal-body', '.log-stream', '.controls-bar', '.btn-action',
            '.hardware-section', '.matrix-table', '.site-footer'
        ]
        for cls_name in classes:
            self.assertIn(cls_name, content, f"Classe obrigatória {cls_name} ausente no CSS")

        # Verifica se media query @media existe
        self.assertIn('@media', content)

    def test_css_syntax_rigor(self):
        content = self.content
        # 1. Chaves balanceadas
        self.assertEqual(content.count('{'), content.count('}'), "Chaves desbalanceadas no CSS")

        # 2. Ausência total de pseudo-código com parênteses em vez de declarações
        invalid_patterns = [
            r'\.terminal-title\s*\(',
            r'\.terminal-body\s*\(',
            r'\.log-stream\s*\(',
            r'\.controls-bar\s*\(',
            r'\.btn-action\s*\(',
            r'\.hardware-section\s*\(',
            r'\.table-card\s*\(',
            r'\.matrix-table\s*\(',
            r'\.site-footer\s*\(',
            r'\.footer-container\s*\(',
            r'\.footer-links\s*\(',
            r'\.footer-copy\s*\('
        ]
        for pat in invalid_patterns:
            self.assertIsNone(re.search(pat, content), f"Pseudo-código detectado: padrão {pat}")

        # 3. Ausência de palavras-chave inválidas ou seletores corrompidos
        self.assertNotIn('reset *', content)
        self.assertNotIn('neon cyan;', content)
        self.assertNotIn('colunas', content)
        self.assertNotIn('purple neon pill', content)
        self.assertNotIn('emerald neon pill', content)

    def test_cyberpunk_design_tokens(self):
        content = self.content
        # Valida glassmorphism real e neon glow
        self.assertIn('backdrop-filter', content)
        self.assertIn('box-shadow', content)
        self.assertIn('linear-gradient', content)
        self.assertIn('repeat(', content)

if __name__ == '__main__':
    unittest.main()

