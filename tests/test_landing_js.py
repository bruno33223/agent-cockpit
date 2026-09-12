import unittest
import os

class TestLandingPage(unittest.TestCase):
    def test_landing_page_exists(self):
        self.assertTrue(os.path.exists('landing-page/app.js'))

    def test_landing_page_size(self):
        self.assertGreater(os.path.getsize('landing-page/app.js'), 0)

    def test_landing_page_initialization(self):
        with open('landing-page/app.js', 'r', encoding='utf-8') as f:
            content = f.read()
        has_init = "initLandingApp" in content or "DOMContentLoaded" in content
        self.assertTrue(has_init, "Deve declarar inicialização com initLandingApp ou DOMContentLoaded.")

    def test_landing_page_simulation(self):
        with open('landing-page/app.js', 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertTrue("Builder" in content or "builder" in content, "Deve conter lógica para simulação de Builders.")
        self.assertTrue("Critic" in content or "critic" in content or "Gauntlet" in content, "Deve conter lógica para Harsh Critics e Gauntlet Loop.")
        self.assertTrue("APROVADO" in content or "verdict" in content or "veredit" in content, "Deve conter emissão de vereditos.")

    def test_landing_page_alternative_tabs(self):
        with open('landing-page/app.js', 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertTrue("switchTab" in content or "tab" in content.lower(), "Deve conter alternância de tabs.")

    def test_landing_page_economy_of_tokens(self):
        with open('landing-page/app.js', 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertTrue("token" in content.lower() or "gpu" in content.lower(), "Deve conter métricas de tokens/GPU.")

if __name__ == '__main__':
    unittest.main()