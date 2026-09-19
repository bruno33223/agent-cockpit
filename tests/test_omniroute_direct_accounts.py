import os
import sys
import json
import time
import socket
import threading
import unittest
from unittest.mock import patch, MagicMock
import urllib.request
import urllib.error
import uvicorn

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from server import opencode_manager
from server.web_server import app

_real_urlopen = urllib.request.urlopen


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestOmniRouteDirectAccounts(unittest.TestCase):
    """
    Testes unitários e de integração para conexão de contas sem chave de API (OAuth/Device/Import).
    """

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
                with _real_urlopen(f"{cls.base_url}/api/health", timeout=1.0) as resp:
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
            cls.server_thread.join(timeout=2.0)

    # -------------------------------------------------------------------------
    # Testes Unitários de Lógica (opencode_manager)
    # -------------------------------------------------------------------------
    def test_list_direct_account_providers(self):
        """Deve listar os provedores compatíveis com conexão direta sem chave de API."""
        providers = opencode_manager.list_omniroute_oauth_providers()
        self.assertIsInstance(providers, list)
        self.assertGreater(len(providers), 0)

        ids = [p["id"] for p in providers]
        self.assertIn("antigravity", ids)
        self.assertIn("claude-code", ids)
        self.assertIn("copilot", ids)
        self.assertIn("cursor", ids)

        # Verifica campos obrigatórios de cada provedor
        for p in providers:
            self.assertIn("id", p)
            self.assertIn("name", p)
            self.assertIn("flow", p)
            self.assertIn("description", p)
            self.assertIn(p["flow"], ["browser", "device", "import"])

    @patch("urllib.request.urlopen")
    def test_start_omniroute_oauth_browser_flow(self, mock_urlopen):
        """Deve chamar endpoint authorize do OmniRoute para fluxos do tipo browser."""
        fake_response = {
            "authUrl": "https://accounts.google.com/o/oauth2/v2/auth?client_id=123",
            "state": "state_abc",
            "codeVerifier": "verifier_123",
            "redirectUri": "http://localhost:8080/callback",
            "flowType": "authorization_code"
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(fake_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_cm

        res = opencode_manager.start_omniroute_oauth(provider_id="antigravity")
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("flow"), "browser")
        self.assertIn("auth_url", res)
        self.assertIn("state", res)
        self.assertIn("code_verifier", res)

    @patch("urllib.request.urlopen")
    def test_start_omniroute_oauth_device_flow(self, mock_urlopen):
        """Deve chamar endpoint device-code do OmniRoute para fluxos do tipo device."""
        fake_response = {
            "device_code": "dev_code_123",
            "user_code": "AFAA-366F",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(fake_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_cm

        res = opencode_manager.start_omniroute_oauth(provider_id="copilot")
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("flow"), "device")
        self.assertEqual(res.get("user_code"), "AFAA-366F")
        self.assertEqual(res.get("verification_uri"), "https://github.com/login/device")

    @patch("urllib.request.urlopen")
    def test_finish_omniroute_oauth(self, mock_urlopen):
        """Deve trocar o código de autorização pela conexão ativa no OmniRoute."""
        fake_response = {
            "connection": {
                "id": "antigravity-account-1",
                "provider": "antigravity",
                "email": "dev@google.com",
                "isActive": True
            }
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(fake_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_cm

        payload = {
            "provider": "antigravity",
            "code": "auth_code_xyz",
            "code_verifier": "verifier_123",
            "redirect_uri": "http://localhost:8080/callback",
            "state": "state_abc"
        }
        res = opencode_manager.finish_omniroute_oauth(payload)
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("account", res)
        self.assertEqual(res["account"].get("provider"), "antigravity")

    @patch("urllib.request.urlopen")
    def test_finish_omniroute_oauth_with_full_url(self, mock_urlopen):
        """Deve extrair code e state automaticamente quando o usuário colar a URL inteira do callback."""
        fake_response = {
            "connection": {
                "id": "antigravity-account-1",
                "provider": "antigravity",
                "email": "dev@google.com",
                "isActive": True
            }
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(fake_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_cm

        # Simula o usuário colando a URL completa do navegador redirecionado para a porta 8080
        full_callback_url = "http://localhost:8080/callback?state=ZKmszU87nlnisU&code=4/0AW_google_code_xyz"
        payload = {
            "provider": "antigravity",
            "code": full_callback_url,
            "code_verifier": "verifier_pkce_123",
            "redirect_uri": "http://localhost:8080/callback"
        }
        res = opencode_manager.finish_omniroute_oauth(payload)
        self.assertEqual(res.get("status"), "ok")

        # Verifica o body enviado para o endpoint de exchange do OmniRoute
        called_req = mock_urlopen.call_args[0][0]
        sent_body = json.loads(called_req.data.decode("utf-8"))
        self.assertEqual(sent_body["code"], "4/0AW_google_code_xyz")
        self.assertEqual(sent_body["state"], "ZKmszU87nlnisU")
        self.assertEqual(sent_body["codeVerifier"], "verifier_pkce_123")

    @patch("urllib.request.urlopen")
    def test_import_omniroute_local_credentials(self, mock_urlopen):
        """Deve disparar auto-importação de credenciais locais (ex: Cursor, Antigravity CLI)."""
        fake_response = {
            "found": True,
            "count": 1,
            "message": "Credenciais importadas com sucesso."
        }
        mock_cm = MagicMock()
        mock_cm.read.return_value = json.dumps(fake_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_cm

        res = opencode_manager.import_omniroute_local_credentials(provider_id="cursor")
        self.assertEqual(res.get("status"), "ok")

    # -------------------------------------------------------------------------
    # Testes de Rotas FastAPI (web_server.py)
    # -------------------------------------------------------------------------
    def test_api_omniroute_oauth_providers(self):
        """GET /api/omniroute/oauth/providers deve retornar a lista de provedores suportados."""
        req = urllib.request.Request(f"{self.base_url}/api/omniroute/oauth/providers")
        with _real_urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.getcode(), 200)
            data = json.loads(resp.read().decode())
            self.assertIn("providers", data)
            self.assertGreater(len(data["providers"]), 0)

    @patch("web_server.opencode_manager.start_omniroute_oauth")
    def test_api_omniroute_oauth_start(self, mock_start):
        """POST /api/omniroute/oauth/start deve delegar para start_omniroute_oauth."""
        mock_start.return_value = {
            "status": "ok",
            "flow": "browser",
            "auth_url": "https://accounts.google.com/oauth",
            "state": "s123",
            "code_verifier": "v123"
        }
        body = json.dumps({"provider": "antigravity"}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/omniroute/oauth/start",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        with _real_urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.getcode(), 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["auth_url"], "https://accounts.google.com/oauth")

    @patch("web_server.opencode_manager.finish_omniroute_oauth")
    def test_api_omniroute_oauth_finish(self, mock_finish):
        """POST /api/omniroute/oauth/finish deve delegar para finish_omniroute_oauth."""
        mock_finish.return_value = {
            "status": "ok",
            "account": {"id": "acc-1", "provider": "antigravity"}
        }
        body = json.dumps({
            "provider": "antigravity",
            "code": "code123",
            "code_verifier": "v123"
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/omniroute/oauth/finish",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        with _real_urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.getcode(), 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["account"]["id"], "acc-1")

    @patch("web_server.opencode_manager.import_omniroute_local_credentials")
    def test_api_omniroute_oauth_import_local(self, mock_import):
        """POST /api/omniroute/oauth/import-local deve delegar para import_omniroute_local_credentials."""
        mock_import.return_value = {
            "status": "ok",
            "count": 1,
            "message": "Credenciais importadas."
        }
        body = json.dumps({"provider": "cursor"}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/omniroute/oauth/import-local",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        with _real_urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.getcode(), 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["count"], 1)


if __name__ == "__main__":
    unittest.main()
