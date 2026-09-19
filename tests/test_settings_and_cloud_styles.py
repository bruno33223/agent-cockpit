import os
import sys
import json
import socket
import threading
import time
import unittest
import urllib.request
import uvicorn

# Configura paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from state_store import db
from web_server import app
from tools.local_builder_tool import execute_local_builder


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestSettingsAndCloudStyles(unittest.TestCase):
    server_thread = None
    server = None
    port = None
    base_url = None

    @classmethod
    def setUpClass(cls):
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        config = uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="error")
        cls.server = uvicorn.Server(config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()

        started = False
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"{cls.base_url}/api/health", timeout=1.0) as resp:
                    if resp.getcode() == 200:
                        started = True
                        break
            except Exception:
                time.sleep(0.1)

        if not started:
            raise RuntimeError("Não foi possível iniciar o servidor de testes uvicorn.")

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.should_exit = True
        if cls.server_thread:
            cls.server_thread.join(timeout=3.0)

    def setUp(self):
        # Garante estado padrão limpo antes de cada teste
        db.switch_current_project("default")
        db.update_settings({
            "enable_local_ai": True,
            "delegate_styles_to_cloud": False,
            "circuit_breaker_threshold": 2
        })
        db.reset_local_worker_attempts("slice-test")
        # Remove arquivos temporários de testes anteriores se existirem
        test_wt = os.path.join(BASE_DIR, ".worktrees", "slice-test")
        if os.path.exists(test_wt):
            import shutil
            shutil.rmtree(test_wt, ignore_errors=True)

    def tearDown(self):
        db.update_settings({
            "enable_local_ai": False,
            "delegate_styles_to_cloud": False
        })
        db.reset_local_worker_attempts("slice-test")
        test_wt = os.path.join(BASE_DIR, ".worktrees", "slice-test")
        if os.path.exists(test_wt):
            import shutil
            shutil.rmtree(test_wt, ignore_errors=True)

    def _http_get(self, endpoint):
        req = urllib.request.Request(f"{self.base_url}{endpoint}", method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.getcode(), data

    def _http_post(self, endpoint, payload):
        req = urllib.request.Request(
            f"{self.base_url}{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.getcode(), data

    def test_state_store_settings_defaults(self):
        """Verifica se get_settings retorna os campos esperados e valores default."""
        settings = db.get_settings()
        self.assertIn("delegate_styles_to_cloud", settings)
        self.assertFalse(settings["delegate_styles_to_cloud"])
        self.assertIn("model", settings)
        self.assertIn("circuit_breaker_threshold", settings)

    def test_state_store_update_settings(self):
        """Verifica se update_settings atualiza e persiste a flag de delegação de estilos."""
        updated = db.update_settings({"delegate_styles_to_cloud": True})
        self.assertTrue(updated["delegate_styles_to_cloud"])

        reloaded = db.get_settings()
        self.assertTrue(reloaded["delegate_styles_to_cloud"])

        cfg = db.get_local_worker_config()
        self.assertTrue(cfg.get("delegate_styles_to_cloud"))

        # Desativa e verifica reversão
        updated_off = db.update_settings({"delegate_styles_to_cloud": False})
        self.assertFalse(updated_off["delegate_styles_to_cloud"])
        self.assertFalse(db.get_settings()["delegate_styles_to_cloud"])

    def test_api_settings_get_and_post(self):
        """Verifica os endpoints REST GET /api/settings e POST /api/settings."""
        status_code, data = self._http_get("/api/settings")
        self.assertEqual(status_code, 200)
        self.assertIn("delegate_styles_to_cloud", data)
        self.assertFalse(data["delegate_styles_to_cloud"])

        # Ativa via POST
        post_code, post_data = self._http_post("/api/settings", {"delegate_styles_to_cloud": True})
        self.assertEqual(post_code, 200)
        self.assertTrue(post_data["delegate_styles_to_cloud"])

        # Verifica via GET
        check_code, check_data = self._http_get("/api/settings")
        self.assertEqual(check_code, 200)
        self.assertTrue(check_data["delegate_styles_to_cloud"])

    def test_execute_local_builder_delegation_to_cloud_for_css(self):
        """
        Verifica se execute_local_builder retorna status DELEGATED_TO_CLOUD quando
        a opção 'DEIXAR ESTILOS COM A NUVEM' está ativa e o arquivo alvo é CSS.
        """
        db.switch_current_project("default")
        db.update_settings({"enable_local_ai": True, "delegate_styles_to_cloud": True})
        db.update_local_worker_config({"enabled": True, "delegate_styles_to_cloud": True})

        res = execute_local_builder(
            slice_id="slice-test",
            instruction="Crie estilos cyberpunk em styles.css",
            target_file="styles.css",
            repo_root=BASE_DIR
        )

        self.assertEqual(res.get("status"), "DELEGATED_TO_CLOUD")
        self.assertEqual(res.get("target_file"), "styles.css")
        self.assertIn("DEIXAR ESTILOS COM A NUVEM", res.get("message", ""))

    def test_execute_local_builder_no_delegation_when_disabled(self):
        """
        Verifica que quando delegate_styles_to_cloud está desativado (False),
        execute_local_builder NÃO retorna DELEGATED_TO_CLOUD para CSS.
        """
        db.update_settings({"delegate_styles_to_cloud": False, "enable_local_ai": True})
        db.update_local_worker_config({"enabled": True})

        res = execute_local_builder(
            slice_id="slice-test",
            instruction="Crie estilos padrão",
            target_file="temp_test_styles.css",
            repo_root=BASE_DIR
        )

        self.assertNotEqual(res.get("status"), "DELEGATED_TO_CLOUD")
        self.assertIn(res.get("status"), ["DELIVERED", "ESCALATION_REQUIRED"])

    def test_execute_local_builder_never_delegates_non_style_files(self):
        """
        Verifica que arquivos de lógica/backend (.py, .js, .json) NUNCA são delegados para nuvem,
        mesmo com a opção delegate_styles_to_cloud ativa.
        """
        db.update_settings({"delegate_styles_to_cloud": True, "enable_local_ai": True})
        db.update_local_worker_config({"enabled": True})

        res = execute_local_builder(
            slice_id="slice-test",
            instruction="Implemente função de ordenação",
            target_file="test_logic.py",
            repo_root=BASE_DIR
        )

        self.assertNotEqual(res.get("status"), "DELEGATED_TO_CLOUD")
        self.assertIn(res.get("status"), ["DELIVERED", "ESCALATION_REQUIRED"])


    def test_execute_local_builder_disabled_by_default(self):
        """
        Verifica que quando enable_local_ai está desativado (padrão),
        execute_local_builder retorna imediatamente DELEGATED_TO_CLOUD para qualquer arquivo
        com aviso de Experimental.
        """
        db.update_settings({"enable_local_ai": False})

        res = execute_local_builder(
            slice_id="slice-test",
            instruction="Crie um utilitário simples",
            target_file="src/utils.py",
            repo_root=BASE_DIR
        )

        self.assertEqual(res.get("status"), "DELEGATED_TO_CLOUD")
        self.assertEqual(res.get("target_file"), "src/utils.py")
        self.assertIn("Experimental", res.get("message", ""))

    def test_api_settings_enable_local_ai_roundtrip(self):
        """Verifica se POST /api/settings com enable_local_ai é persistido e refletido no GET."""
        post_code, post_data = self._http_post("/api/settings", {"enable_local_ai": True})
        self.assertEqual(post_code, 200)
        self.assertTrue(post_data["enable_local_ai"])

        get_code, get_data = self._http_get("/api/settings")
        self.assertEqual(get_code, 200)
        self.assertTrue(get_data["enable_local_ai"])

        # Desativa
        post_code2, post_data2 = self._http_post("/api/settings", {"enable_local_ai": False})
        self.assertEqual(post_code2, 200)
        self.assertFalse(post_data2["enable_local_ai"])

    def test_omniroute_connectors_container_in_index_html(self):
        """Verifica se web/index.html possui container para listagem visual de conectores OmniRoute no modal de configurações."""
        html_path = os.path.join(BASE_DIR, "web", "index.html")
        self.assertTrue(os.path.exists(html_path), "index.html não encontrado")
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()

        # O container deve estar no modal de configurações (ag-panel-models)
        self.assertIn('id="ag-omniroute-connectors-list"', content)
        self.assertIn('ag-omniroute-connectors-section', content)

    def test_omniroute_connectors_logic_in_settings_js(self):
        """Verifica se web/js/settings.js possui as funções para carregar, renderizar conectores e auto-preencher OpenCode."""
        js_path = os.path.join(BASE_DIR, "web", "js", "settings.js")
        self.assertTrue(os.path.exists(js_path), "settings.js não encontrado")
        with open(js_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("loadOmniRouteConnectors", content)
        self.assertIn("renderOmniRouteConnectors", content)
        self.assertIn("autofillOpenCodeCredentials", content)


if __name__ == "__main__":
    unittest.main()



    def test_settings_js_imports_and_state_reference(self):
        """Garante que web/js/settings.js importa state de state.js e nao lanca ReferenceError."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        js_path = os.path.join(base_dir, "web", "js", "settings.js")
        with open(js_path, "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("import { apiFetch, currentProjectId, state } from './state.js'", js)
        self.assertIn("typeof state !== 'undefined'", js)
    def test_settings_js_imports_and_state_reference(self):
        """Garante que web/js/settings.js importa state de state.js e nao lanca ReferenceError."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        js_path = os.path.join(base_dir, "web", "js", "settings.js")
        with open(js_path, "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("import { apiFetch, currentProjectId, state } from './state.js';", js)
        self.assertIn("state && state.human_gates", js)

if __name__ == '__main__':
    unittest.main()
