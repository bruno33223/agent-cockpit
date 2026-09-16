import os
import sys
import json
import time
import socket
import threading
import unittest
import urllib.request
import urllib.error
import uvicorn

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from web_server import app


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestCustomizationsAPI(unittest.TestCase):
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

    def _http_request(self, endpoint, method="GET", payload=None):
        url = f"{self.base_url}{endpoint}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                return resp.getcode(), resp_data
        except urllib.error.HTTPError as e:
            try:
                err_data = json.loads(e.read().decode("utf-8"))
            except Exception:
                err_data = {"error": str(e)}
            return e.code, err_data

    def test_mcp_crud_and_toggle(self):
        """Testa o ciclo completo de MCP: GET, POST, PUT, TOGGLE e DELETE."""
        # 1. GET lista inicial
        status, data = self._http_request("/api/customizations/mcp", method="GET")
        self.assertEqual(status, 200)
        self.assertIn("mcp_servers", data)
        self.assertIsInstance(data["mcp_servers"], list)

        # 2. POST com payload inválido (sem comando no stdio)
        status, data = self._http_request(
            "/api/customizations/mcp",
            method="POST",
            payload={"id": "bad-mcp", "type": "stdio"}
        )
        self.assertEqual(status, 400)

        # 3. POST criar novo servidor MCP stdio
        mcp_payload = {
            "id": "test-fs-mcp",
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "env": {"DEBUG": "1"},
            "enabled": True,
            "description": "Servidor MCP de Teste Filesystem"
        }
        status, data = self._http_request("/api/customizations/mcp", method="POST", payload=mcp_payload)
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "success")
        self.assertIn("mcp_server", data)
        self.assertEqual(data["mcp_server"]["id"], "test-fs-mcp")

        # 4. GET deve conter o novo servidor criado
        status, data = self._http_request("/api/customizations/mcp", method="GET")
        self.assertEqual(status, 200)
        ids = [s.get("id") or s.get("name") for s in data["mcp_servers"]]
        self.assertIn("test-fs-mcp", ids)

        # 5. PUT atualizar MCP existente
        update_payload = {
            "description": "Descrição Atualizada",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home"]
        }
        status, data = self._http_request("/api/customizations/mcp/test-fs-mcp", method="PUT", payload=update_payload)
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data["mcp_server"]["description"], "Descrição Atualizada")

        # 6. PUT em MCP inexistente retorna 404
        status, data = self._http_request("/api/customizations/mcp/mcp-inexistente", method="PUT", payload={"description": "x"})
        self.assertEqual(status, 404)

        # 7. POST toggle MCP
        status, data = self._http_request("/api/customizations/mcp/test-fs-mcp/toggle", method="POST")
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "success")
        self.assertFalse(data.get("enabled"))

        # Toggle de volta
        status, data = self._http_request("/api/customizations/mcp/test-fs-mcp/toggle", method="POST")
        self.assertEqual(status, 200)
        self.assertTrue(data.get("enabled"))

        # 8. DELETE MCP
        status, data = self._http_request("/api/customizations/mcp/test-fs-mcp", method="DELETE")
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "success")

        # 9. DELETE MCP já excluído retorna 404
        status, data = self._http_request("/api/customizations/mcp/test-fs-mcp", method="DELETE")
        self.assertEqual(status, 404)

    def test_skills_crud_and_toggle(self):
        """Testa o ciclo completo de Skills: GET, POST, PUT, TOGGLE e DELETE."""
        # 1. GET lista inicial
        status, data = self._http_request("/api/customizations/skills", method="GET")
        self.assertEqual(status, 200)
        self.assertIn("skills", data)
        self.assertIsInstance(data["skills"], list)

        # 2. POST validação: nome vazio retorna 400
        status, data = self._http_request(
            "/api/customizations/skills",
            method="POST",
            payload={"name": "   ", "description": "vazio"}
        )
        self.assertEqual(status, 400)

        # 3. POST criar nova skill
        skill_payload = {
            "name": "super-analyst",
            "description": "Skill de Análise Profunda",
            "content": "---\nname: super-analyst\ndescription: Skill de Análise\n---\n# Instruções da Skill",
            "enabled": True
        }
        status, data = self._http_request("/api/customizations/skills", method="POST", payload=skill_payload)
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "success")
        self.assertIn("skill", data)
        self.assertEqual(data["skill"]["name"], "super-analyst")

        # 4. GET deve conter a nova skill
        status, data = self._http_request("/api/customizations/skills", method="GET")
        self.assertEqual(status, 200)
        names = [s.get("name") for s in data["skills"]]
        self.assertIn("super-analyst", names)

        # 5. PUT atualizar skill existente
        status, data = self._http_request(
            "/api/customizations/skills/super-analyst",
            method="PUT",
            payload={"description": "Descrição Reformulada"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data["skill"]["description"], "Descrição Reformulada")

        # 6. PUT em skill inexistente retorna 404
        status, data = self._http_request(
            "/api/customizations/skills/skill-fantasma",
            method="PUT",
            payload={"description": "inexistente"}
        )
        self.assertEqual(status, 404)

        # 7. POST toggle skill
        status, data = self._http_request("/api/customizations/skills/super-analyst/toggle", method="POST")
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "success")
        self.assertFalse(data.get("enabled"))

        # Toggle de volta
        status, data = self._http_request("/api/customizations/skills/super-analyst/toggle", method="POST")
        self.assertEqual(status, 200)
        self.assertTrue(data.get("enabled"))

        # 8. DELETE skill
        status, data = self._http_request("/api/customizations/skills/super-analyst", method="DELETE")
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "success")

        # 9. DELETE skill inexistente retorna 404
        status, data = self._http_request("/api/customizations/skills/super-analyst", method="DELETE")
        self.assertEqual(status, 404)

    def test_mcp_sse_validation(self):
        """Valida que MCPs do tipo SSE/HTTP exigem URL válida."""
        status, data = self._http_request(
            "/api/customizations/mcp",
            method="POST",
            payload={"id": "sse-invalid", "type": "sse"}
        )
        self.assertEqual(status, 400)

        # SSE válido com URL
        status, data = self._http_request(
            "/api/customizations/mcp",
            method="POST",
            payload={"id": "sse-valid", "type": "sse", "url": "http://127.0.0.1:8080/sse"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["mcp_server"]["url"], "http://127.0.0.1:8080/sse")

        # Cleanup
        self._http_request("/api/customizations/mcp/sse-valid", method="DELETE")

    def test_customizations_sync(self):
        """Testa o endpoint de sincronização imediata POST /api/customizations/sync."""
        status, data = self._http_request("/api/customizations/sync", method="POST")
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "success")
        self.assertTrue(data.get("synced"))


if __name__ == "__main__":
    unittest.main()
