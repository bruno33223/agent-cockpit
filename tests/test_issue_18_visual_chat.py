import unittest
import os

class TestIssue18VisualChat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html_path = os.path.join(base_dir, 'web', 'index.html')
        cls.chat_js_path = os.path.join(base_dir, 'web', 'js', 'opencode_chat.js')
        cls.app_js_path = os.path.join(base_dir, 'web', 'app.js')
        cls.term_ws_path = os.path.join(base_dir, 'web', 'js', 'terminal_workspace.js')
        cls.css_path = os.path.join(base_dir, 'web', 'styles.css')

        with open(cls.html_path, 'r', encoding='utf-8') as f:
            cls.html_content = f.read()

        if os.path.exists(cls.chat_js_path):
            with open(cls.chat_js_path, 'r', encoding='utf-8') as f:
                cls.chat_js_content = f.read()
        else:
            cls.chat_js_content = ""

        if os.path.exists(cls.app_js_path):
            with open(cls.app_js_path, 'r', encoding='utf-8') as f:
                cls.app_js_content = f.read()
        else:
            cls.app_js_content = ""

        if os.path.exists(cls.term_ws_path):
            with open(cls.term_ws_path, 'r', encoding='utf-8') as f:
                cls.term_ws_content = f.read()
        else:
            cls.term_ws_content = ""

        if os.path.exists(cls.css_path):
            with open(cls.css_path, 'r', encoding='utf-8') as f:
                cls.css_content = f.read()
        else:
            cls.css_content = ""

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

    def test_app_js_imports_and_initializes_opencode_chat(self):
        """Valida que web/app.js importa e inicializa o chat visual de forma integrada."""
        self.assertTrue(os.path.exists(self.app_js_path), "web/app.js deve existir")
        app_js = self.app_js_content

        self.assertIn('opencode_chat.js', app_js,
                      "web/app.js deve importar o módulo opencode_chat.js")
        self.assertIn('initOpenCodeChat', app_js,
                      "web/app.js deve importar e inicializar initOpenCodeChat")
        self.assertIn('safeInit("initOpenCodeChat", initOpenCodeChat)', app_js,
                      "web/app.js deve inicializar o chat via safeInit dentro de bootstrapCockpit")
        self.assertIn('openCodeChat', app_js,
                      "web/app.js deve expor e exportar openCodeChat")

    def test_terminal_workspace_handles_visual_chat_action(self):
        """Valida que web/js/terminal_workspace.js intercepta open-visual-chat sem invocar createSession."""
        self.assertTrue(os.path.exists(self.term_ws_path), "web/js/terminal_workspace.js deve existir")
        ws_js = self.term_ws_content

        self.assertIn('open-visual-chat', ws_js,
                      "web/js/terminal_workspace.js deve checar a ação open-visual-chat")
        self.assertIn('openCodeChat', ws_js,
                      "web/js/terminal_workspace.js deve referenciar e chamar openCodeChat")

        # Verifica que o handler tem um early return para não chamar createSession
        idx_action = ws_js.find("action === 'open-visual-chat'")
        self.assertNotEqual(idx_action, -1, "Deve existir verificação para action === 'open-visual-chat'")
        
        # O trecho seguinte deve conter .open() e return antes de this.createSession
        action_snippet = ws_js[idx_action:idx_action + 600]
        self.assertIn('.open()', action_snippet, "Deve chamar .open() ao receber open-visual-chat")
        self.assertIn('return;', action_snippet, "Deve retornar para não executar createSession")

    def test_styles_css_contains_visual_chat_classes(self):
        """Valida que web/styles.css contém estilos completos integrados ao tema dark."""
        self.assertTrue(os.path.exists(self.css_path), "web/styles.css deve existir")
        css = self.css_content

        required_selectors = [
            '.opencode-visual-chat-container',
            '.opencode-chat-header',
            '.opencode-chat-messages',
            '.opencode-chat-card',
            '.role-badge',
            '.opencode-thinking-box',
            '.thinking-box',
            '.opencode-chat-textarea',
            '.opencode-chat-input'
        ]

        for selector in required_selectors:
            self.assertIn(selector, css, f"web/styles.css deve conter a regra para {selector}")

if __name__ == '__main__':
    unittest.main()

