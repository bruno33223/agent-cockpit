import unittest
import os
import re

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SLICES_CHAT_JS_PATH = os.path.join(BASE_DIR, "web", "js", "slices_chat.js")

class TestIssue19FrontendXSS(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.exists(SLICES_CHAT_JS_PATH), f"Arquivo não encontrado: {SLICES_CHAT_JS_PATH}")
        with open(SLICES_CHAT_JS_PATH, "r", encoding="utf-8") as f:
            self.js_content = f.read()

    def test_no_inline_onclick_interpolation(self):
        """Valida que slices_chat.js não contém inline onclick com interpolação de strings não sanitizadas."""
        # Não deve haver interpolação direta inline como onclick="openDrawer('${node.id}')"
        self.assertNotIn(
            "onclick=\"openDrawer('${node.id}')\"",
            self.js_content,
            "Encontrado padrão vulnerável onclick=\"openDrawer('${node.id}')\" em slices_chat.js"
        )
        # Nenhuma chamada inline onclick deve interpolar ${node.id}
        pattern = re.compile(r"onclick=[\"'].*?\$\{node\.id\}.*?[\"']")
        match = pattern.search(self.js_content)
        self.assertIsNone(
            match,
            f"Encontrado onclick vulnerável com interpolação inline: {match.group(0) if match else ''}"
        )

    def test_secure_data_attribute_used(self):
        """Valida que o botão de inspeção usa data-node-id com escapeHtml seguro."""
        self.assertIn(
            'data-node-id="${escapeHtml(node.id)}"',
            self.js_content,
            "O elemento deve usar atributo data-node-id com escapeHtml seguro: data-node-id=\"${escapeHtml(node.id)}\""
        )

    def test_event_delegation_or_listener_present(self):
        """Valida que existe delegação de eventos ou addEventListener para os botões de inspeção."""
        # Deve haver listener delegado ou evento de clique associado ao data-node-id ou btn-inspect
        has_delegation = (
            "btn-inspect" in self.js_content and
            ("addEventListener" in self.js_content or "onclick" not in self.js_content) and
            ("dataset.nodeId" in self.js_content or "getAttribute('data-node-id')" in self.js_content)
        )
        self.assertTrue(
            has_delegation,
            "Não foi encontrada delegação de eventos segura para o botão btn-inspect / data-node-id"
        )

if __name__ == "__main__":
    unittest.main()
