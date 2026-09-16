import unittest
import os

class TestIssue15UIStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html_path = os.path.join(base_dir, 'web', 'index.html')
        cls.css_path = os.path.join(base_dir, 'web', 'styles.css')

        with open(cls.html_path, 'r', encoding='utf-8') as f:
            cls.html_content = f.read()

        with open(cls.css_path, 'r', encoding='utf-8') as f:
            cls.css_content = f.read()

    def test_huggingface_search_containers_in_html(self):
        """Valida que web/index.html possui os containers de busca no Hugging Face Hub."""
        html = self.html_content
        self.assertIn('id="hf-search-input"', html, "Input de busca Hugging Face #hf-search-input deve existir no HTML")
        self.assertIn('id="hf-search-results"', html, "Container de resultados #hf-search-results deve existir no HTML")
        self.assertIn('modal-model-download', html, "Deve estar contido dentro do modal de modelos")

    def test_huggingface_card_and_quantization_styles_in_css(self):
        """Valida que web/styles.css possui classes de estilo para os cards HF, contadores, quantizações e feedback."""
        css = self.css_content
        # Cards e listas
        self.assertIn('.hf-search-results', css, "Classe .hf-search-results deve existir no CSS")
        self.assertIn('.hf-model-card', css, "Classe .hf-model-card deve existir no CSS")
        
        # Metadados: downloads e likes
        self.assertTrue('.hf-downloads' in css or '.hf-stat-downloads' in css, "Classe para downloads deve existir no CSS")
        self.assertTrue('.hf-likes' in css or '.hf-stat-likes' in css, "Classe para likes deve existir no CSS")
        
        # Badges de quantização
        self.assertTrue('.hf-quant-badge' in css or '.quant-badge' in css, "Classe para badges de quantização deve existir no CSS")
        
        # Feedback de download
        self.assertTrue('.hf-download-feedback' in css or '.hf-download-status' in css, "Classe para feedback de download deve existir no CSS")

if __name__ == '__main__':
    unittest.main()
