import unittest
import os

class TestIssue18VisualChat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html_path = os.path.join(base_dir, 'web', 'index.html')
        cls.chat_js_path = os.path.join(base_dir, 'web', 'js', 'opencode_chat.js')

        with open(cls.html_path, 'r', encoding='utf-8') as f:
            cls.html_content = f.read()

        if os.path.exists(cls.chat_js_path):
            with open(cls.chat_js_path, 'r', encoding='utf-8') as f:
                cls.chat_js_content = f.read()
        else:
            cls.chat_js_content = ""

    def test_html_visual_chat_container_structure(self):
        """Valida que web/index.html possui o container do Chat Visual com lista de mensagens, input e botão."""
        html = self.html_content

        self.assertIn('id="opencode-visual-chat-container"', html,
                      "web/index.html deve conter o container #opencode-visual-chat-container")
        self.assertIn('id="opencode-chat-messages"', html,
                      "web/index.html deve conter o elemento de mensagens #opencode-chat-messages")
        self.assertIn('id="opencode-chat-input"', html,
                      "web/index.html deve conter o campo de input/textarea #opencode-chat-input")
        self.assertIn('id="btn-send-opencode-chat"', html,
                      "web/index.html deve conter o botão de envio #btn-send-opencode-chat")

    def test_html_new_terminal_menu_visual_chat_option(self):
        """Valida que o menu de novo terminal possui a opção de Chat Visual (OpenCode)."""
        html = self.html_content
        self.assertTrue(
            'data-terminal-type="opencode-visual"' in html or
            'Chat Visual' in html or
            'data-action="open-visual-chat"' in html,
            "Menu de novo terminal deve ter opção para Chat Visual (OpenCode)"
        )

    def test_opencode_chat_js_exists_and_implements_core_features(self):
        """Valida que web/js/opencode_chat.js existe e implementa os requisitos de inicialização, envio, renderização e escape."""
        self.assertTrue(os.path.exists(self.chat_js_path), "web/js/opencode_chat.js deve existir")
        js = self.chat_js_content

        # Inicialização
        self.assertIn('initOpenCodeChat', js, "Deve implementar a função initOpenCodeChat")

        # Endpoint de envio de mensagem
        self.assertIn('/api/opencode/headless/message', js,
                      "Deve conter chamada ao endpoint /api/opencode/headless/message")

        # Renderização de cards de mensagem
        self.assertTrue(
            'renderMessage' in js or 'appendChatMessage' in js or 'addMessage' in js,
            "Deve conter função para renderização de cards de mensagem"
        )

        # Timestamps
        self.assertTrue(
            'timestamp' in js.lower() or 'toLocaleTimeString' in js,
            "Deve incluir tratamento/renderização de timestamp nas mensagens"
        )

        # Badges de papel (role badges)
        self.assertTrue(
            'role' in js.lower() and ('badge' in js.lower() or 'role-badge' in js.lower()),
            "Deve incluir badges de papel (role badges)"
        )

        # Escape seguro de HTML
        self.assertTrue(
            'escapeHtml' in js or 'escape' in js.lower() or 'replace(/&/g' in js,
            "Deve utilizar escape seguro de HTML para evitar XSS"
        )

if __name__ == '__main__':
    unittest.main()
