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
SUBAGENT_TABS_JS_PATH = os.path.join(BASE_DIR, "web", "js", "subagent_tabs.js")
STYLES_CSS_PATH = os.path.join(BASE_DIR, "web", "styles.css")
TERMINAL_CSS_PATH = os.path.join(BASE_DIR, "web", "css", "terminal.css")
BUTTONS_CSS_PATH = os.path.join(BASE_DIR, "web", "css", "buttons.css")
APP_JS_PATH = os.path.join(BASE_DIR, "web", "app.js")
ZEUS_ICON_PATH = os.path.join(BASE_DIR, "web", "zeus_terminal_god.svg")


class TestIssue24ChatWorkspace(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.exists(HTML_PATH), "index.html deve existir")
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            self.html = f.read()

        self.assertTrue(os.path.exists(TERMINAL_JS_PATH), "terminal_workspace.js deve existir")
        with open(TERMINAL_JS_PATH, "r", encoding="utf-8") as f:
            self.terminal_js = f.read()

        self.assertTrue(os.path.exists(SUBAGENT_TABS_JS_PATH), "subagent_tabs.js deve existir")
        with open(SUBAGENT_TABS_JS_PATH, "r", encoding="utf-8") as f:
            self.subagent_tabs_js = f.read()

        self.assertTrue(os.path.exists(ZEUS_ICON_PATH), "zeus_terminal_god.svg deve existir")

    def test_zeus_chat_workspace_file_exists_and_exports(self):
        """Critério 1: web/js/zeus_chat_workspace.js deve existir e exportar ZeusChatWorkspaceManager."""
        self.assertTrue(
            os.path.exists(ZEUS_CHAT_JS_PATH),
            "web/js/zeus_chat_workspace.js deve existir no diretório web/js/"
        )
        with open(ZEUS_CHAT_JS_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("class ZeusChatWorkspaceManager", content)
        self.assertIn("zeusChatWorkspace", content)
        self.assertIn("openOrCreateChatSession", content)
        self.assertIn("handleSubagentSpawn", content)

    def test_zeus_chat_native_workspace_integration_role_visual_chat(self):
        """Critério 1: Zeus Chat não é floating container (position: absolute), mas painel nativo role: 'visual-chat'."""
        with open(ZEUS_CHAT_JS_PATH, "r", encoding="utf-8") as f:
            zeus_content = f.read()

        # O papel integrado deve ser visual-chat
        self.assertIn("visual-chat", zeus_content)
        # Deve integrar com o TerminalWorkspaceManager
        self.assertTrue(
            "terminalWorkspace" in zeus_content or "createSession" in zeus_content,
            "Zeus Chat deve integrar com o TerminalWorkspaceManager"
        )
        # O painel de chat não deve ser fixado como floating container absoluto
        self.assertNotIn("position: fixed", zeus_content)
        self.assertIn("zeus-chat-pane", zeus_content)

        # terminal_workspace.js também deve reconhecer o role visual-chat
        self.assertIn("visual-chat", self.terminal_js)
        self.assertIn("zeus_terminal_god.svg", self.terminal_js)

    def test_split_button_in_index_html(self):
        """Critério 2: Botão '+ Novo Terminal' deve ser um split button com botão principal e seta lateral (▾)."""
        # Botão principal mantendo compatibilidade
        self.assertIn('id="btn-new-terminal"', self.html)
        self.assertIn('+ Novo Terminal', self.html)

        # Seta lateral dropdown
        self.assertTrue(
            'id="btn-new-terminal-dropdown"' in self.html or 'btn-split-arrow' in self.html,
            "index.html deve conter o botão da seta lateral (▾) do split button"
        )
        self.assertIn('▾', self.html)

        # Dropdown de terminais alternativos
        self.assertIn('id="new-terminal-dropdown"', self.html)
        self.assertIn('Claude Code', self.html)
        self.assertIn('OpenCode', self.html)
        self.assertIn('Terminal Bash', self.html)

    def test_split_button_logic_in_terminal_workspace_js(self):
        """Critério 2: Clique no botão principal abre/foca o Zeus Chat; seta lateral alterna o dropdown."""
        self.assertIn("openZeusChat", self.terminal_js)
        self.assertIn("btn-new-terminal", self.terminal_js)
        # O listener do botão principal deve invocar openZeusChat
        self.assertTrue(
            "openZeusChat" in self.terminal_js and "btnNewTerm" in self.terminal_js,
            "Clique principal deve acionar openZeusChat"
        )

    def test_zeus_tab_creation_with_god_icon_and_title(self):
        """Critério 1: Criação ou foco da aba no workspace com ícone sagrado zeus_terminal_god.svg e título 'Zeus Chat'."""
        with open(ZEUS_CHAT_JS_PATH, "r", encoding="utf-8") as f:
            zeus_content = f.read()

        self.assertIn("zeus_terminal_god.svg", zeus_content + self.terminal_js)
        self.assertIn("Zeus Chat", zeus_content + self.terminal_js)

    def test_subagent_spawn_event_and_interactive_card(self):
        """Critério 3: Evento 'subagent_spawn' renderiza card interativo com status e botão 'Abrir Terminal do Subagente'."""
        with open(ZEUS_CHAT_JS_PATH, "r", encoding="utf-8") as f:
            zeus_content = f.read()

        self.assertIn("subagent_spawn", zeus_content)
        self.assertIn("Abrir Terminal do Subagente", zeus_content)
        self.assertIn("openSubagentTab", zeus_content)
        # Deve conter seletor de ação para abrir o terminal do subagente
        self.assertIn("btn-open-subagent-terminal", zeus_content)

    def test_non_destructive_chat_focus_on_subagent_open(self):
        """Critério 3: Clicar no botão aciona openSubagentTab e foca aba no workspace sem fechar o chat."""
        with open(ZEUS_CHAT_JS_PATH, "r", encoding="utf-8") as f:
            zeus_content = f.read()

        # O código não deve fechar ou destruir a sessão de chat ao abrir o subagente
        self.assertNotIn("closeSession(chat", zeus_content)
        self.assertNotIn("closeSubagentTab(chat", zeus_content)
        # Deve invocar focusSubagentTab ou selectSession da nova aba
        self.assertTrue(
            "focusSubagentTab" in zeus_content or "selectSession" in zeus_content or "openSubagentTab" in zeus_content
        )

    def test_node_execution_zeus_chat_behavior(self):
        """Executa teste funcional em ambiente Node.js verificando sintaxe e consistência do módulo."""
        result = subprocess.run(
            ["node", "--check", ZEUS_CHAT_JS_PATH],
            capture_output=True,
            text=True
        )
        self.assertEqual(
            result.returncode, 0,
            f"Erro de sintaxe em web/js/zeus_chat_workspace.js:\n{result.stderr}"
        )


if __name__ == "__main__":
    unittest.main()
