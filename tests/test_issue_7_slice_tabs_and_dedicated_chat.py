import unittest
import tempfile
import os
import json
import time

from server.state_store import StateStore
from server.mcp_server import handle_tool_call, TOOLS_DEFINITIONS

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_JS_PATH = os.path.join(BASE_DIR, "web", "app.js")
SLICES_CHAT_JS_PATH = os.path.join(BASE_DIR, "web", "js", "slices_chat.js")
INDEX_HTML_PATH = os.path.join(BASE_DIR, "web", "index.html")
STYLES_CSS_PATH = os.path.join(BASE_DIR, "web", "styles.css")

class TestIssue7SliceTabsAndDedicatedChat(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = StateStore(states_dir=self.tmpdir.name)
        # Inicializa projeto default com 3 fatias
        self.db.sync_epic(
            epic_name="Projeto com Fatias Granulares",
            goal="Testar abas de fatias e chats dedicados",
            vertical_slices=[
                {
                    "id": "slice-1",
                    "title": "Fatia 1: Infraestrutura e Banco",
                    "spec_md": "Especificação da fatia 1",
                    "acceptance_criteria": "Critérios da fatia 1"
                },
                {
                    "id": "slice-2",
                    "title": "Fatia 2: Regras de Negócio e Serviços",
                    "spec_md": "Especificação da fatia 2",
                    "acceptance_criteria": "Critérios da fatia 2"
                },
                {
                    "id": "slice-3",
                    "title": "Fatia 3: Frontend e Integração",
                    "spec_md": "Especificação da fatia 3",
                    "acceptance_criteria": "Critérios da fatia 3"
                }
            ],
            project_id="test-proj"
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_add_steering_message_with_slice_id(self):
        """Valida armazenamento e associação de slice_id em mensagens do usuário e do orquestrador."""
        msg_global = self.db.add_user_steering("Mensagem geral do projeto", project_id="test-proj")
        self.assertIsNone(msg_global.get("slice_id"))

        msg_slice1 = self.db.add_user_steering("Focar na migração do banco SQLite", project_id="test-proj", slice_id="slice-1")
        self.assertEqual(msg_slice1.get("slice_id"), "slice-1")
        self.assertEqual(msg_slice1.get("sender"), "USER")

        msg_slice2_orch = self.db.post_orchestrator_message("Especificação da fatia 2 validada", project_id="test-proj", slice_id="slice-2", sender="ORCHESTRATOR")
        self.assertEqual(msg_slice2_orch.get("slice_id"), "slice-2")
        self.assertEqual(msg_slice2_orch.get("sender"), "ORCHESTRATOR")

        state = self.db.get_state("test-proj")
        messages = state.get("steering_messages", [])
        self.assertEqual(len(messages), 4) # 1 inicial + 3 novas

    def test_fetch_unconsumed_steering_isolation_by_slice(self):
        """Valida que o consumo de mensagens por slice_id isola os agentes de diferentes fatias."""
        # Mensagens para diferentes fatias
        self.db.add_user_steering("Direcionamento para Fatia 1", project_id="test-proj", slice_id="slice-1")
        self.db.add_user_steering("Direcionamento para Fatia 2", project_id="test-proj", slice_id="slice-2")
        self.db.add_user_steering("Alerta Global para Todos", project_id="test-proj", slice_id=None)

        # Agente da fatia 1 busca mensagens
        unconsumed_s1 = self.db.fetch_unconsumed_steering(project_id="test-proj", slice_id="slice-1")
        texts_s1 = [m["text"] for m in unconsumed_s1]
        self.assertIn("Direcionamento para Fatia 1", texts_s1)
        self.assertNotIn("Direcionamento para Fatia 2", texts_s1)

        # Agente da fatia 2 busca mensagens
        unconsumed_s2 = self.db.fetch_unconsumed_steering(project_id="test-proj", slice_id="slice-2")
        texts_s2 = [m["text"] for m in unconsumed_s2]
        self.assertIn("Direcionamento para Fatia 2", texts_s2)
        self.assertNotIn("Direcionamento para Fatia 1", texts_s2)

    def test_get_slice_steering_messages(self):
        """Valida filtragem histórica de mensagens por fatia no backend."""
        self.db.add_user_steering("Msg Slice 1", project_id="test-proj", slice_id="slice-1")
        self.db.add_user_steering("Msg Slice 2", project_id="test-proj", slice_id="slice-2")
        self.db.post_orchestrator_message("Orch Slice 1", project_id="test-proj", slice_id="slice-1")

        s1_msgs = self.db.get_slice_steering_messages(project_id="test-proj", slice_id="slice-1")
        self.assertEqual(len(s1_msgs), 2)
        self.assertTrue(all(m.get("slice_id") == "slice-1" for m in s1_msgs))

        s2_msgs = self.db.get_slice_steering_messages(project_id="test-proj", slice_id="slice-2")
        self.assertEqual(len(s2_msgs), 1)
        self.assertEqual(s2_msgs[0]["text"], "Msg Slice 2")

    def test_mcp_tools_slice_steering_integration(self):
        """Valida que as ferramentas MCP fetch_user_steering e post_orchestrator_message suportam slice_id."""
        import server.mcp_server as mcp_mod
        original_db = mcp_mod.db
        mcp_mod.db = self.db

        try:
            # Verifica schema registrado
            tools_by_name = {t["name"]: t for t in TOOLS_DEFINITIONS}
            fetch_schema = tools_by_name["fetch_user_steering"]["inputSchema"]["properties"]
            post_schema = tools_by_name["post_orchestrator_message"]["inputSchema"]["properties"]

            self.assertIn("slice_id", fetch_schema)
            self.assertIn("slice_id", post_schema)
            self.assertIn("sender", post_schema)

            # Envia steering para slice-1
            self.db.add_user_steering("Instrução MCP para Fatia 1", project_id="test-proj", slice_id="slice-1")

            # Executa tool fetch_user_steering para slice-1
            res_s1 = handle_tool_call("fetch_user_steering", {"project_id": "test-proj", "slice_id": "slice-1"})
            self.assertIn("Instrução MCP para Fatia 1", res_s1["content"][0]["text"])

            # Executa tool post_orchestrator_message com slice_id
            res_post = handle_tool_call("post_orchestrator_message", {
                "message": "Orquestrador atualizou fatia 1",
                "project_id": "test-proj",
                "slice_id": "slice-1",
                "sender": "ORCHESTRATOR"
            })
            self.assertIn("sucesso", res_post["content"][0]["text"].lower())

            # Confirma no estado
            msgs = self.db.get_slice_steering_messages(project_id="test-proj", slice_id="slice-1")
            self.assertTrue(any(m["text"] == "Orquestrador atualizou fatia 1" for m in msgs))
        finally:
            mcp_mod.db = original_db

    def test_frontend_slice_tabs_and_chat_structure(self):
        """Valida componentes de abas de slices e chat dedicado em HTML, JS e CSS."""
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            html = f.read()
        with open(SLICES_CHAT_JS_PATH, "r", encoding="utf-8") as f:
            js = f.read()
        with open(STYLES_CSS_PATH, "r", encoding="utf-8") as f:
            css = f.read()

        # HTML deve conter navegação de abas de slices e containers correspondentes
        self.assertIn("slice-tabs-nav", html)
        self.assertIn("slice-tab-pane-global", html)
        self.assertIn("slice-tab-pane-detail", html)

        # JS deve conter lógica de alternância e renderização de abas de fatia
        self.assertIn("renderSliceTabs", js)
        self.assertIn("renderDedicatedSliceView", js)
        self.assertIn("activeSliceTabId", js)

        # CSS deve conter estilização para abas de slices e container de chat dedicado
        self.assertIn(".slice-tabs-nav", css)
        self.assertIn(".slice-tab-btn", css)
        self.assertIn(".slice-detail-grid", css)
        self.assertIn(".slice-gov-card", css)
        self.assertIn(".slice-chat-container", css)

if __name__ == "__main__":
    unittest.main()
