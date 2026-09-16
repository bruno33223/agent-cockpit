import unittest
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TERMINAL_JS_PATH = os.path.join(BASE_DIR, "web", "js", "terminal_workspace.js")
SUBAGENT_TABS_JS_PATH = os.path.join(BASE_DIR, "web", "js", "subagent_tabs.js")
STYLES_CSS_PATH = os.path.join(BASE_DIR, "web", "styles.css")

class TestIssue18SubagentTabs(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.exists(TERMINAL_JS_PATH), "terminal_workspace.js deve existir")
        with open(TERMINAL_JS_PATH, "r", encoding="utf-8") as f:
            self.terminal_js = f.read()

        self.assertTrue(os.path.exists(STYLES_CSS_PATH), "styles.css deve existir")
        with open(STYLES_CSS_PATH, "r", encoding="utf-8") as f:
            self.styles_css = f.read()

    def test_terminal_workspace_offers_visual_chat_opencode_option(self):
        """Valida que web/js/terminal_workspace.js oferece no dropdown/botão de criação a opção 'Chat Visual (OpenCode)'."""
        self.assertIn(
            "Chat Visual (OpenCode)",
            self.terminal_js,
            "web/js/terminal_workspace.js deve oferecer no dropdown/botão a opção 'Chat Visual (OpenCode)'"
        )

    def test_subagent_tabs_implements_open_subagent_tab(self):
        """Valida que web/js/subagent_tabs.js implementa openSubagentTab(subagentInfo) com título, badge e terminal isolado."""
        self.assertTrue(
            os.path.exists(SUBAGENT_TABS_JS_PATH),
            "web/js/subagent_tabs.js deve existir"
        )
        with open(SUBAGENT_TABS_JS_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # Deve implementar a função openSubagentTab
        self.assertIn("function openSubagentTab", content)
        # Deve receber subagentInfo e formatar título descritivo (ex: '🤖 [Builder] slice-1')
        self.assertIn("Builder", content)
        self.assertIn("subagentInfo", content)
        # Deve incluir badge de status
        self.assertIn("subagent-badge", content)
        # Deve gerenciar ou criar terminal isolado
        self.assertTrue("createSession" in content or "terminal" in content.lower())

    def test_styles_css_contains_subagent_and_opencode_selectors(self):
        """Valida que web/styles.css contém os seletores .subagent-tab, .subagent-badge e .opencode-chat-panel."""
        self.assertIn(
            ".subagent-tab",
            self.styles_css,
            "web/styles.css deve conter seletor .subagent-tab"
        )
        self.assertIn(
            ".subagent-badge",
            self.styles_css,
            "web/styles.css deve conter seletor .subagent-badge"
        )
        self.assertIn(
            ".opencode-chat-panel",
            self.styles_css,
            "web/styles.css deve conter seletor .opencode-chat-panel"
        )

if __name__ == "__main__":
    unittest.main()
