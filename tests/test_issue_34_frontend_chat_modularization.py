import os
import sys
import unittest
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

CHAT_CORE_JS = os.path.join(BASE_DIR, "web", "js", "chat", "zeus_chat_core.js")
MESSAGE_RENDERER_JS = os.path.join(BASE_DIR, "web", "js", "chat", "message_renderer.js")
SUBAGENT_CARD_RENDERER_JS = os.path.join(BASE_DIR, "web", "js", "chat", "subagent_card_renderer.js")
WORKSPACE_JS = os.path.join(BASE_DIR, "web", "js", "zeus_chat_workspace.js")
UI_JS = os.path.join(BASE_DIR, "web", "js", "zeus_chat_ui.js")
INDEX_HTML = os.path.join(BASE_DIR, "web", "index.html")

TARGET_FILES = {
    "zeus_chat_core.js": CHAT_CORE_JS,
    "message_renderer.js": MESSAGE_RENDERER_JS,
    "subagent_card_renderer.js": SUBAGENT_CARD_RENDERER_JS,
    "zeus_chat_workspace.js": WORKSPACE_JS,
    "zeus_chat_ui.js": UI_JS,
}

MAX_LINES = 250


class TestIssue34FrontendChatModularization(unittest.TestCase):
    """Testes TDD para a Issue #34 - Deduplicação e Arquitetura Modular do Zeus Chat."""

    def test_01_modules_exist_and_exports(self):
        """Critério 1: Novos módulos em web/js/chat/ devem existir e exportar classes/funções requeridas."""
        for name, path in TARGET_FILES.items():
            self.assertTrue(os.path.exists(path), f"Arquivo obrigatório não existe: {name} em {path}")

        with open(CHAT_CORE_JS, "r", encoding="utf-8") as f:
            core_content = f.read()
        self.assertIn("class ZeusChatCore", core_content, "zeus_chat_core.js deve exportar ZeusChatCore")

        with open(MESSAGE_RENDERER_JS, "r", encoding="utf-8") as f:
            msg_content = f.read()
        self.assertIn("class MessageRenderer", msg_content, "message_renderer.js deve exportar MessageRenderer")

        with open(SUBAGENT_CARD_RENDERER_JS, "r", encoding="utf-8") as f:
            sub_content = f.read()
        self.assertIn("class SubagentCardRenderer", sub_content, "subagent_card_renderer.js deve exportar SubagentCardRenderer")

    def test_02_sloc_under_250_lines(self):
        """Critério 2: Nenhum dos arquivos resultantes deve exceder 250 linhas."""
        for name, path in TARGET_FILES.items():
            self.assertTrue(os.path.exists(path), f"Arquivo não encontrado para verificação de linhas: {name}")
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            line_count = len(lines)
            self.assertLessEqual(
                line_count,
                MAX_LINES,
                f"Arquivo {name} possui {line_count} linhas, excedendo o limite estrito de {MAX_LINES} linhas!"
            )

    def test_03_index_html_script_order(self):
        """Critério 3: web/index.html deve incluir os novos scripts na ordem correta antes dos scripts dependentes."""
        self.assertTrue(os.path.exists(INDEX_HTML), "web/index.html deve existir")
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            html = f.read()

        # Verifica menção aos módulos modulares ou imports em index.html
        self.assertIn("zeus_chat_core.js", html, "index.html deve referenciar zeus_chat_core.js")
        self.assertIn("message_renderer.js", html, "index.html deve referenciar message_renderer.js")
        self.assertIn("subagent_card_renderer.js", html, "index.html deve referenciar subagent_card_renderer.js")

        idx_core = html.find("zeus_chat_core.js")
        idx_msg = html.find("message_renderer.js")
        idx_sub = html.find("subagent_card_renderer.js")
        idx_app = html.find("app.js")

        # Os scripts modulares devem vir antes de app.js se incluídos via tag script
        if idx_app != -1:
            self.assertLess(idx_core, idx_app, "zeus_chat_core.js deve ser carregado antes de app.js")
            self.assertLess(idx_msg, idx_app, "message_renderer.js deve ser carregado antes de app.js")
            self.assertLess(idx_sub, idx_app, "subagent_card_renderer.js deve ser carregado antes de app.js")

    def test_04_separation_of_responsibilities(self):
        """Critério 4: Validação de SOLID e separação de responsabilidades entre os módulos."""
        # zeus_chat_core.js: Lida com streaming SSE, API, áudio, modelos
        with open(CHAT_CORE_JS, "r", encoding="utf-8") as f:
            core = f.read()
        self.assertIn("/api/zeus-chat/message", core, "zeus_chat_core.js deve gerenciar requisições da API de chat")
        self.assertIn("isVisionSupported", core, "zeus_chat_core.js deve conter lógica de suporte à visão")

        # message_renderer.js: Lida com tags de pensamento e cards de ferramenta
        with open(MESSAGE_RENDERER_JS, "r", encoding="utf-8") as f:
            msg = f.read()
        self.assertIn("zeus-thinking-box", msg, "message_renderer.js deve renderizar blocos de pensamento")
        self.assertIn("zeus-tool-card", msg, "message_renderer.js deve renderizar cards de ferramentas")

        # subagent_card_renderer.js: Lida com cards de subagentes e botões de terminal
        with open(SUBAGENT_CARD_RENDERER_JS, "r", encoding="utf-8") as f:
            sub = f.read()
        self.assertIn("btn-open-subagent-terminal", sub, "subagent_card_renderer.js deve renderizar botão de terminal")
        self.assertTrue("target_files" in sub or "targetFiles" in sub, "subagent_card_renderer.js deve suportar target_files")

        # zeus_chat_workspace.js: Casca de workspace
        with open(WORKSPACE_JS, "r", encoding="utf-8") as f:
            ws = f.read()
        self.assertIn("class ZeusChatWorkspaceManager", ws, "zeus_chat_workspace.js deve manter ZeusChatWorkspaceManager")
        self.assertIn("class ZeusChatSessionController", ws, "zeus_chat_workspace.js deve manter ZeusChatSessionController")

        # zeus_chat_ui.js: Casca de painel lateral/modal
        with open(UI_JS, "r", encoding="utf-8") as f:
            ui = f.read()
        self.assertIn("class ZeusChatUI", ui, "zeus_chat_ui.js deve manter ZeusChatUI")

    def test_05_syntax_check_node(self):
        """Critério 5: Validação de sintaxe JS via Node.js em todos os arquivos modificados e criados."""
        for name, path in TARGET_FILES.items():
            if os.path.exists(path):
                res = subprocess.run(["node", "--check", path], capture_output=True, text=True)
                self.assertEqual(res.returncode, 0, f"Erro de sintaxe em {name}:\n{res.stderr}")


if __name__ == "__main__":
    unittest.main()
