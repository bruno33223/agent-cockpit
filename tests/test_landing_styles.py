import os
import unittest


class TestLandingStyles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Localiza o arquivo CSS relativo ao workspace do teste
        cls.workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cls.css_path = os.path.join(cls.workspace_dir, "landing-page", "styles.css")
        cls.css_exists = os.path.exists(cls.css_path)
        cls.css_content = ""
        if cls.css_exists:
            with open(cls.css_path, "r", encoding="utf-8") as f:
                cls.css_content = f.read()

    def test_css_file_exists_and_not_empty(self):
        """Verifica se landing-page/styles.css existe e possui tamanho > 0 bytes."""
        self.assertTrue(self.css_exists, f"Arquivo não encontrado: {self.css_path}")
        self.assertGreater(os.path.getsize(self.css_path), 0, "O arquivo styles.css está vazio (0 bytes).")
        self.assertGreater(len(self.css_content.strip()), 0, "O conteúdo de styles.css não deve ser apenas espaços em branco.")

    def test_root_css_variables(self):
        """Verifica se define variáveis CSS em :root (fundo escuro e acentos neon cyan/purple/emerald)."""
        self.assertIn(":root", self.css_content, "styles.css deve conter bloco de variáveis globais :root.")
        
        # Variáveis de tema escuro e acentos neon cyberpunk
        lower_content = self.css_content.lower()
        self.assertTrue(
            "--bg" in lower_content or "background" in lower_content,
            "Deve conter variáveis ou definições de background escuro no :root."
        )
        self.assertTrue(
            "#00f0ff" in lower_content or "cyan" in lower_content or "--cyan" in lower_content,
            "Deve conter cor de destaque neon cyan (#00f0ff ou variável)."
        )
        self.assertTrue(
            "#a855f7" in lower_content or "purple" in lower_content or "--purple" in lower_content,
            "Deve conter cor de destaque neon purple (#a855f7 ou variável)."
        )
        self.assertTrue(
            "#10b981" in lower_content or "emerald" in lower_content or "--emerald" in lower_content,
            "Deve conter cor de destaque neon emerald (#10b981 ou variável)."
        )

    def test_required_component_selectors(self):
        """Verifica a presença dos seletores essenciais: .hero, .glass-card, .agent-node, .btn-primary, .terminal-preview."""
        required_selectors = [
            ".hero",
            ".glass-card",
            ".agent-node",
            ".btn-primary",
            ".terminal-preview"
        ]
        for selector in required_selectors:
            self.assertIn(selector, self.css_content, f"Seletor CSS obrigatório não encontrado: {selector}")

    def test_glassmorphism_effects(self):
        """Verifica se há propriedades de glassmorphism (backdrop-filter)."""
        self.assertIn("backdrop-filter", self.css_content, "Deve conter efeito glassmorphism com backdrop-filter.")

    def test_media_queries_responsiveness(self):
        """Verifica a presença de regras de responsividade com @media query."""
        self.assertIn("@media", self.css_content, "styles.css deve conter regras de responsividade @media query.")


if __name__ == '__main__':
    unittest.main()