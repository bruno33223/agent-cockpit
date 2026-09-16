import os
import sys
import json
import unittest
from unittest.mock import patch

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import opencode_manager
import web_server


class TestIssue19CredentialsAndCORS(unittest.TestCase):
    """
    Testes para Issue #19:
    1. Endpoints e funções públicas de credenciais retornam chaves mascaradas (sk-***).
    2. opencode.json está listado no .gitignore.
    3. CORS não permite allow_origins=['*'] junto com allow_credentials=True.
    """

    def test_gitignore_contains_opencode_json_and_local_keys(self):
        """Garante que opencode.json e arquivos de chaves locais estão protegidos no .gitignore."""
        gitignore_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".gitignore"))
        self.assertTrue(os.path.exists(gitignore_path), ".gitignore deve existir")
        with open(gitignore_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines() if line.strip() and not line.startswith("#")]
        
        self.assertIn("opencode.json", lines, "opencode.json deve estar explicitamente listado no .gitignore")

    def test_detect_opencode_credentials_masks_api_key(self):
        """Garante que detect_opencode_credentials mascara chaves de API retornadas."""
        env_vars = {
            "OMNIROUTE_URL": "http://localhost:20128/v1",
            "OMNIROUTE_API_KEY": "sk-real-secret-key-123456789",
            "OPENCODE_MODEL": "test-model"
        }
        with patch.dict(os.environ, env_vars, clear=True):
            detected = opencode_manager.detect_opencode_credentials()
            api_key = detected.get("api_key")
            self.assertIsNotNone(api_key)
            self.assertNotEqual(api_key, "sk-real-secret-key-123456789")
            self.assertTrue(api_key.startswith("sk-***") or "..." in api_key or api_key.endswith("***") or "sk-" in api_key,
                            f"Chave exposta sem mascaramento: {api_key}")
            # Verifica que a chave real não está presente em texto limpo
            self.assertNotIn("123456789", api_key)
            self.assertTrue("*" in api_key)

    def test_api_opencode_credentials_endpoint_masks_api_key(self):
        """Verifica que o endpoint GET /api/opencode/credentials retorna chaves mascaradas."""
        env_vars = {
            "OMNIROUTE_URL": "http://localhost:20128/v1",
            "OMNIROUTE_API_KEY": "sk-super-secret-token-9999",
            "OPENCODE_MODEL": "test-model"
        }
        with patch.dict(os.environ, env_vars, clear=True):
            res = web_server.get_opencode_credentials()
            api_key = res.get("api_key")
            self.assertIsNotNone(api_key)
            self.assertNotEqual(api_key, "sk-super-secret-token-9999")
            self.assertNotIn("token-9999", api_key)
            self.assertTrue("*" in api_key)

    def test_cors_security_policy_not_wildcard_with_credentials(self):
        """
        Verifica que a política de CORS não permite allow_origins=['*'] junto com allow_credentials=True.
        """
        # Inspeciona os middlewares registrados no FastAPI
        cors_middlewares = [
            m for m in web_server.app.user_middleware 
            if "CORSMiddleware" in str(m.cls)
        ]
        self.assertTrue(len(cors_middlewares) > 0, "Deve haver CORSMiddleware configurado")

        for mw in cors_middlewares:
            options = mw.kwargs
            allow_origins = options.get("allow_origins", [])
            allow_credentials = options.get("allow_credentials", False)

            # Regra fundamental de segurança CORS:
            # allow_origins=['*'] NUNCA deve ser combinado com allow_credentials=True
            if "*" in allow_origins:
                self.assertFalse(
                    allow_credentials,
                    "Inseguro: CORSMiddleware possui allow_origins=['*'] com allow_credentials=True!"
                )
            if allow_credentials:
                self.assertNotIn(
                    "*",
                    allow_origins,
                    "Inseguro: allow_credentials=True requer origens explicitas (ex: localhost, 127.0.0.1), não wildcard '*'"
                )


if __name__ == "__main__":
    unittest.main()
