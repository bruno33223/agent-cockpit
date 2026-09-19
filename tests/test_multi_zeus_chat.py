"""
test_multi_zeus_chat.py: Testes automatizados para validação de Zeus Chat Ilimitado,
remoção de opções redundantes no menu dropdown (+ Novo Terminal) e unificação do papel
de Orquestrador no Zeus Chat.
"""

import os
import sys
import unittest
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

HTML_PATH = os.path.join(BASE_DIR, "web", "index.html")
TERMINAL_JS_PATH = os.path.join(BASE_DIR, "web", "js", "terminal_workspace.js")
ZEUS_CHAT_JS_PATH = os.path.join(BASE_DIR, "web", "js", "zeus_chat_workspace.js")
SERVER_ZEUS_ENGINE_PATH = os.path.join(BASE_DIR, "server", "zeus_chat_engine.py")


class TestMultiZeusChat(unittest.TestCase):
    def setUp(self):
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            self.html = f.read()

        with open(TERMINAL_JS_PATH, "r", encoding="utf-8") as f:
            self.terminal_js = f.read()

        with open(ZEUS_CHAT_JS_PATH, "r", encoding="utf-8") as f:
            self.zeus_chat_js = f.read()

        with open(SERVER_ZEUS_ENGINE_PATH, "r", encoding="utf-8") as f:
            self.server_engine = f.read()

    def test_new_terminal_dropdown_items_cleaned(self):
        """Verifica que 'Chat Visual (OpenCode)' e 'Orquestrador Zeus' (bash) foram removidos do dropdown visível."""
        # Localiza o container visível do dropdown
        dropdown_start = self.html.find('id="new-terminal-dropdown"')
        self.assertNotEqual(dropdown_start, -1, "Dropdown #new-terminal-dropdown deve existir")
        dropdown_end = self.html.find('<!-- COMPATIBILIDADE DEFENSIVA', dropdown_start)
        dropdown_html = self.html[dropdown_start:dropdown_end]

        # Não deve conter 'Chat Visual (OpenCode)' no dropdown visível
        self.assertNotIn("Chat Visual (OpenCode)", dropdown_html,
                         "Chat Visual (OpenCode) não deve estar no dropdown visível")
        self.assertNotIn('data-terminal-type="opencode-visual"', dropdown_html,
                         "opencode-visual não deve estar no dropdown visível")

        # Não deve conter a opção separada bash de Orquestrador Zeus no dropdown visível
        self.assertNotIn("Staff Orchestrator Blueprint", dropdown_html,
                         "Opção separada de terminal bash do Orquestrador não deve estar no dropdown visível")

        # Deve conter Zeus Chat (Orquestrador) como primeira opção
        self.assertIn("Zeus Chat (Orquestrador)", dropdown_html)
        self.assertIn('data-terminal-type="zeus-chat"', dropdown_html)

    def test_zeus_chat_workspace_multi_instance_support(self):
        """Valida que zeus_chat_workspace.js implementa arquitetura multi-instância e session controllers."""
        self.assertIn("class ZeusChatSessionController", self.zeus_chat_js)
        self.assertIn("class ZeusChatWorkspaceManager", self.zeus_chat_js)
        self.assertIn("this.sessions = new Map()", self.zeus_chat_js)
        self.assertIn("attachPane(session, elPane)", self.zeus_chat_js)
        self.assertIn("closeSession(sessionId)", self.zeus_chat_js)
        self.assertIn("openOrCreateChatSession", self.zeus_chat_js)

    def test_terminal_workspace_unlimited_zeus_chat_creation(self):
        """Valida que terminal_workspace.js gera IDs únicos e permite criação concorrente ilimitada de Zeus Chats."""
        self.assertIn("zeus-chat-${Date.now()}-${this.counter}", self.terminal_js)
        self.assertIn("openZeusChat", self.terminal_js)
        # openZeusChat não deve estar limitado a buscar sessão existente apenas
        self.assertIn("createSession", self.terminal_js)

    def test_backend_default_orchestrator_system_prompt(self):
        """Valida que o backend possui DEFAULT_ZEUS_SYSTEM_PROMPT consolidando papel de Staff Orchestrator."""
        self.assertIn("DEFAULT_ZEUS_SYSTEM_PROMPT", self.server_engine)
        self.assertIn("Staff Orchestrator", self.server_engine)
        self.assertIn("effective_system_prompt = system_prompt or DEFAULT_ZEUS_SYSTEM_PROMPT", self.server_engine)

    def test_js_syntax_validation(self):
        """Valida sintaxe dos arquivos JS modificados com Node.js."""
        for path in [TERMINAL_JS_PATH, ZEUS_CHAT_JS_PATH]:
            res = subprocess.run(["node", "--check", path], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Erro de sintaxe em {path}: {res.stderr}")


if __name__ == "__main__":
    unittest.main()
