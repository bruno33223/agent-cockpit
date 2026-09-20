"""
tests/test_issue_25_auth_endpoints.py
Testes de conformidade e integração para a Fatia 1 da Issue #25:
[Auth] Componente de Login do Cockpit — endpoints públicos /api/auth/verify e /api/auth/config.

Cobre:
1. Middleware HTTP 401 sem token quando auth é requerida (COCKPIT_REQUIRE_AUTH=1).
2. 200 com token válido via header X-Cockpit-Token.
3. Endpoint público /api/auth/verify validando tokens sem nunca retornar 401.
4. Endpoint público /api/auth/config sem vazamento do token.
5. Endpoint /api/auth/status mantido público.
6. Retrocompatibilidade: sem env definido, auth não é requerida.
7. Geração do arquivo states/session_token.txt com permissões 0600.
"""

import os
import sys
import json
import time
import socket
import threading
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
import uvicorn

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import auth


def find_free_port() -> int:
    """Encontra uma porta TCP livre no localhost para teste de servidor."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class TestIssue25AuthEndpoints(unittest.TestCase):
    """Testes de integração HTTP dos endpoints de autenticação (auth requerida por env)."""

    TOKEN = "test-token-123"
    server_thread = None
    server = None
    port = None
    base_url = None

    @classmethod
    def setUpClass(cls):
        os.environ["COCKPIT_REQUIRE_AUTH"] = "1"
        os.environ["COCKPIT_AUTH_TOKEN"] = cls.TOKEN

        import web_server
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        config = uvicorn.Config(web_server.app, host="127.0.0.1", port=cls.port, log_level="error")
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
        os.environ.pop("COCKPIT_REQUIRE_AUTH", None)
        os.environ.pop("COCKPIT_AUTH_TOKEN", None)

    def _http_get(self, endpoint: str, headers: dict = None):
        req = urllib.request.Request(f"{self.base_url}{endpoint}", headers=headers or {}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.getcode(), json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode("utf-8"))
            except Exception:
                return e.code, {}

    def test_401_without_token_when_auth_required(self):
        """Sem token, rota protegida deve retornar 401 quando auth é requerida."""
        code, _ = self._http_get("/api/projects")
        self.assertEqual(code, 401)

    def test_200_with_valid_token(self):
        """Com token válido via X-Cockpit-Token, rota protegida deve retornar 200."""
        code, data = self._http_get("/api/projects", {"X-Cockpit-Token": self.TOKEN})
        self.assertEqual(code, 200)
        self.assertIn("projects", data)

    def test_verify_endpoint_public_validates_token(self):
        """GET /api/auth/verify deve nunca retornar 401 e validar o token informado."""
        # Sem token
        code, data = self._http_get("/api/auth/verify")
        self.assertEqual(code, 200)
        self.assertTrue(data.get("auth_required"))
        self.assertFalse(data.get("valid"))

        # Token errado
        code, data = self._http_get("/api/auth/verify", {"X-Cockpit-Token": "token-errado"})
        self.assertEqual(code, 200)
        self.assertTrue(data.get("auth_required"))
        self.assertFalse(data.get("valid"))

        # Token certo
        code, data = self._http_get("/api/auth/verify", {"X-Cockpit-Token": self.TOKEN})
        self.assertEqual(code, 200)
        self.assertTrue(data.get("auth_required"))
        self.assertTrue(data.get("valid"))

    def test_config_endpoint_public_no_token_leak(self):
        """GET /api/auth/config é público e não deve vazar o valor do token."""
        code, data = self._http_get("/api/auth/config")
        self.assertEqual(code, 200)
        self.assertTrue(data.get("auth_required"))
        self.assertEqual(data.get("token_source"), "env")
        body = json.dumps(data)
        self.assertNotIn(self.TOKEN, body)

    def test_auth_status_public(self):
        """GET /api/auth/status deve continuar público informando auth_required/authenticated."""
        code, data = self._http_get("/api/auth/status")
        self.assertEqual(code, 200)
        self.assertTrue(data.get("auth_required"))
        self.assertFalse(data.get("authenticated"))

    def test_no_auth_required_by_default(self):
        """Sem env de auth, rotas funcionam sem token e verify reporta auth_required=false."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COCKPIT_REQUIRE_AUTH", None)
            os.environ.pop("COCKPIT_AUTH_TOKEN", None)

            code, data = self._http_get("/api/projects")
            self.assertEqual(code, 200)
            self.assertIn("projects", data)

            code, data = self._http_get("/api/auth/verify")
            self.assertEqual(code, 200)
            self.assertTrue(data.get("valid"))
            self.assertFalse(data.get("auth_required"))


class TestIssue25SessionTokenFile(unittest.TestCase):
    """Testes unitários diretos de server/auth.py (sem subir servidor)."""

    def test_session_token_file_created_with_0600(self):
        """get_or_create_session_token deve criar session_token.txt com conteúdo e permissão 0600."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("COCKPIT_REQUIRE_AUTH", None)
                os.environ.pop("COCKPIT_AUTH_TOKEN", None)

                mgr = auth.AuthManager(token_storage_dir=tmp_dir)
                token = mgr.get_or_create_session_token()

                token_file = os.path.join(tmp_dir, "session_token.txt")
                self.assertTrue(os.path.exists(token_file), "session_token.txt deve ser criado")

                with open(token_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                self.assertNotEqual(content, "", "Conteúdo do arquivo de token não pode estar vazio")
                self.assertEqual(content, token)

                mode = os.stat(token_file).st_mode & 0o777
                self.assertEqual(mode, 0o600, "Permissão do arquivo de token deve ser 0600")


if __name__ == "__main__":
    unittest.main()