import unittest
import os

class TestLandingPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html_path = os.path.join(cls.base_dir, 'landing-page', 'index.html')
        cls.content = ""
        if os.path.exists(cls.html_path):
            with open(cls.html_path, 'r', encoding='utf-8') as f:
                cls.content = f.read()

    def test_landing_page_exists(self):
        self.assertTrue(os.path.exists(self.html_path), "landing-page/index.html deve existir")

    def test_landing_page_size(self):
        self.assertTrue(os.path.exists(self.html_path), "Arquivo landing-page/index.html não encontrado")
        self.assertGreater(os.path.getsize(self.html_path), 0, "O tamanho do arquivo deve ser maior que 0 bytes")

    def test_landing_page_doctype(self):
        self.assertTrue(os.path.exists(self.html_path), "Arquivo landing-page/index.html não encontrado")
        self.assertIn('<!DOCTYPE html>', self.content, "Deve conter <!DOCTYPE html>")

    def test_landing_page_title(self):
        self.assertTrue(os.path.exists(self.html_path), "Arquivo landing-page/index.html não encontrado")
        self.assertIn('Agent Cockpit', self.content, "Título ou conteúdo deve conter 'Agent Cockpit'")
        self.assertIn('<title>', self.content, "Deve conter tag <title>")

    def test_landing_page_meta_viewport(self):
        self.assertTrue(os.path.exists(self.html_path), "Arquivo landing-page/index.html não encontrado")
        self.assertIn('name="viewport"', self.content, "Deve conter meta viewport")

    def test_landing_page_stylesheets(self):
        self.assertTrue(os.path.exists(self.html_path), "Arquivo landing-page/index.html não encontrado")
        self.assertIn('styles.css', self.content, "Deve conter link para styles.css")

    def test_landing_page_app_js(self):
        self.assertTrue(os.path.exists(self.html_path), "Arquivo landing-page/index.html não encontrado")
        self.assertIn('app.js', self.content, "Deve conter script app.js")

    def test_landing_page_hero(self):
        self.assertTrue(os.path.exists(self.html_path), "Arquivo landing-page/index.html não encontrado")
        self.assertIn('id="hero"', self.content, "Deve conter seção hero com id='hero'")

    def test_landing_page_architecture(self):
        self.assertTrue(os.path.exists(self.html_path), "Arquivo landing-page/index.html não encontrado")
        self.assertIn('id="architecture"', self.content, "Deve conter seção architecture com id='architecture'")
        self.assertTrue('3x3' in self.content, "Deve mencionar arquitetura 3x3")
        self.assertTrue('Gauntlet' in self.content, "Deve mencionar Gauntlet Loop")

    def test_landing_page_features(self):
        self.assertTrue(os.path.exists(self.html_path), "Arquivo landing-page/index.html não encontrado")
        self.assertIn('id="features"', self.content, "Deve conter seção features com id='features'")

    def test_landing_page_simulator(self):
        self.assertTrue(os.path.exists(self.html_path), "Arquivo landing-page/index.html não encontrado")
        self.assertIn('id="simulator"', self.content, "Deve conter seção simulator com id='simulator'")

    def test_landing_page_local_worker_gpu(self):
        self.assertTrue(os.path.exists(self.html_path), "Arquivo landing-page/index.html não encontrado")
        self.assertIn('id="local-worker"', self.content, "Deve conter seção local worker com id='local-worker'")

    def test_landing_page_footer(self):
        self.assertTrue(os.path.exists(self.html_path), "Arquivo landing-page/index.html não encontrado")
        self.assertIn('<footer', self.content, "Deve conter tag footer semântica")

if __name__ == '__main__':
    unittest.main()