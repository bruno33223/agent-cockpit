import os
import re
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_WORKER_JS_PATH = os.path.join(BASE_DIR, "web", "js", "local_worker.js")


class TestIssue15LocalWorkerHF(unittest.TestCase):
    """
    Testes de validação da Integração Hugging Face no Local Worker Frontend (Issue #15).
    Verifica a presença de lógica de busca via API HF com debounce,
    renderização dos cards de modelos com metadados (autor, título, downloads, likes, quantizações)
    e o acionamento do botão 'Baixar Modelo' chamando pullLocalModel(tag).
    """

    @classmethod
    def setUpClass(cls):
        cls.assertTrue(
            os.path.exists(LOCAL_WORKER_JS_PATH),
            f"Arquivo {LOCAL_WORKER_JS_PATH} não encontrado."
        )
        with open(LOCAL_WORKER_JS_PATH, "r", encoding="utf-8") as f:
            cls.js_content = f.read()

    def test_hf_search_api_call_and_debounce(self):
        """Verifica se local_worker.js contém a integração de busca chamando /api/local-worker/hf-search com debounce."""
        # Deve chamar o endpoint da API de busca no Hugging Face
        self.assertIn(
            "/api/local-worker/hf-search",
            self.js_content,
            "Endpoint /api/local-worker/hf-search deve ser chamado em web/js/local_worker.js"
        )

        # Deve implementar mecanismo de debounce para a digitação de busca
        has_debounce = (
            "debounce" in self.js_content.lower()
            or "searchtimeout" in self.js_content.lower()
            or ("cleartimeout" in self.js_content.lower() and "settimeout" in self.js_content.lower())
        )
        self.assertTrue(
            has_debounce,
            "Deve existir controle de debounce (clearTimeout/setTimeout) na busca de modelos do Hugging Face"
        )

    def test_hf_cards_rendering_and_container(self):
        """Verifica a renderização dos cards de resultados no container #hf-search-results."""
        # Deve referenciar o container #hf-search-results
        self.assertIn(
            "hf-search-results",
            self.js_content,
            "Container #hf-search-results deve ser referenciado em web/js/local_worker.js"
        )

        # Deve renderizar metadados essenciais nos cards: autor, título/id, downloads, likes e quantizações
        self.assertTrue(
            "downloads" in self.js_content.lower(),
            "Cards de resultado do Hugging Face devem exibir número de downloads"
        )
        self.assertTrue(
            "likes" in self.js_content.lower(),
            "Cards de resultado do Hugging Face devem exibir número de likes"
        )
        self.assertTrue(
            "quant" in self.js_content.lower() or "quantization" in self.js_content.lower() or "quantizations" in self.js_content.lower(),
            "Cards de resultado do Hugging Face devem exibir badges de quantização (ex: GGUF/Q4_K_M)"
        )

    def test_hf_pull_action_trigger(self):
        """Verifica se o botão de ação 'Baixar Modelo' chama pullLocalModel(tag)."""
        # Deve ter o botão com label 'Baixar Modelo' ou ação de download associada aos cards
        self.assertTrue(
            "Baixar Modelo" in self.js_content or "pullLocalModel" in self.js_content,
            "Deve haver ação para baixar o modelo chamando pullLocalModel"
        )
        # Deve conectar a ação do card chamando pullLocalModel passando a tag do modelo
        self.assertIn(
            "pullLocalModel",
            self.js_content,
            "Deve haver chamada de pullLocalModel"
        )

        # Deve conter função ou lógica dedicada para renderização dos resultados HF
        has_hf_render = (
            "renderhf" in self.js_content.lower()
            or "searchhuggingface" in self.js_content.lower()
            or "searchhf" in self.js_content.lower()
        )
        self.assertTrue(
            has_hf_render,
            "Deve existir função dedicada para busca ou renderização de resultados do Hugging Face"
        )


if __name__ == "__main__":
    unittest.main()
