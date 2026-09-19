"""
tests/test_issue_38_security_hardening.py
Suíte de testes para a Issue #38:
[Security & Hardening] Autenticação local na API, saneamento de comandos no Test Runner e desindexação de opencode.json

Critérios de Aceitação Cobertos:
1. Desindexação de opencode.json do Git e presença de opencode.json.example seguro.
2. Saneamento e validação estrita de comandos no test_runner (shlex.split, shell=False, bloqueio de injeções).
3. Autenticação HTTP local via AuthManager (X-Cockpit-Token, Bearer token, rotas públicas vs protegidas, 401).
4. Autenticação WebSocket /ws via query param (?token=...) com fechamento 1008 se não autorizado.
5. Retrocompatibilidade total quando autenticação estiver desativada.
"""

import os
import sys
import json
import time
import socket
import asyncio
import threading
import tempfile
import unittest
import subprocess
import urllib.request
import urllib.error
import websockets
import uvicorn

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_DIR = os.path.join(REPO_ROOT, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import test_runner


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class TestIssue38GitAndCredentials(unittest.TestCase):
    """Validação da desindexação de opencode.json e arquivo de exemplo."""

    def test_opencode_json_not_tracked_in_git(self):
        """Garante que opencode.json NÃO está rastreado no Git (git ls-files)."""
        proc = subprocess.run(
            ["git", "ls-files", "opencode.json"],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(
            proc.stdout.strip(),
            "",
            f"opencode.json ainda está rastreado no git: {proc.stdout.strip()}"
        )

    def test_opencode_json_example_exists_and_is_valid(self):
        """Garante que opencode.json.example existe na raiz com placeholders seguros e sem credenciais reais."""
        example_path = os.path.join(REPO_ROOT, "opencode.json.example")
        self.assertTrue(
            os.path.exists(example_path),
            "Arquivo opencode.json.example deve existir na raiz do repositório"
        )
        with open(example_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("$schema", data)
        self.assertIn("provider", data)
        raw_content = json.dumps(data)
        self.assertNotIn("sk-ant-", raw_content)
        self.assertNotIn("ghp_", raw_content)

    def test_gitignore_contains_opencode_json(self):
        """Garante que o .gitignore contém regra para opencode.json."""
        gitignore_path = os.path.join(REPO_ROOT, ".gitignore")
        self.assertTrue(os.path.exists(gitignore_path))
        with open(gitignore_path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
        self.assertIn("opencode.json", lines)


class TestIssue38TestRunnerSanitization(unittest.TestCase):
    """Validação de sanitização e proteção contra execução arbitrária no test_runner."""

    def test_sanitize_and_validate_allowed_executors(self):
        """Valida que comandos com executores permitidos são decompostos em listas seguras."""
        valid_commands = [
            ("pytest tests/", ["pytest", "tests/"]),
            ("python -m unittest discover tests", ["python", "-m", "unittest", "discover", "tests"]),
            ("python3 -m pytest -v", ["python3", "-m", "pytest", "-v"]),
            ("npm test", ["npm", "test"]),
            ("yarn test --runInBand", ["yarn", "test", "--runInBand"]),
            ("cargo test --workspace", ["cargo", "test", "--workspace"]),
            ("dotnet test", ["dotnet", "test"]),
            ("go test ./...", ["go", "test", "./..."]),
            ("vitest run", ["vitest", "run"]),
            ("jest --coverage", ["jest", "--coverage"]),
            ("pnpm test", ["pnpm", "test"]),
            ("npx vitest run", ["npx", "vitest", "run"]),
            ("mvn test", ["mvn", "test"]),
            ("gradle test", ["gradle", "test"])
        ]

        self.assertTrue(
            hasattr(test_runner, "sanitize_and_validate_test_command"),
            "test_runner deve possuir a função sanitize_and_validate_test_command"
        )

        for raw_cmd, expected_tokens in valid_commands:
            tokens = test_runner.sanitize_and_validate_test_command(raw_cmd)
            self.assertEqual(tokens, expected_tokens, f"Falha ao validar comando legítimo: {raw_cmd}")

    def test_sanitize_and_validate_rejects_dangerous_characters_and_chains(self):
        """Valida que encadeamentos de comandos e injeções de shell são terminantemente rejeitados."""
        dangerous_commands = [
            "pytest tests; rm -rf /",
            "pytest && echo 'hacked'",
            "pytest || curl http://127.0.0.1",
            "pytest | grep fail",
            "python3 test.py & echo 'background'",
            "pytest $(whoami)",
            "pytest `id`",
            "pytest tests > /tmp/malicious.txt",
            "pytest tests < /dev/zero",
            "pytest tests 2>&1",
            "; cat /etc/passwd",
            "&& rm -rf /",
            "| nc -lvp 4444",
            "pytest tests\nrm -rf /",
            "pytest tests\r\ncalc.exe",
            ""
        ]

        for cmd in dangerous_commands:
            with self.assertRaises(ValueError, msg=f"Comando perigoso não foi rejeitado: {cmd}"):
                test_runner.sanitize_and_validate_test_command(cmd)

    def test_sanitize_and_validate_rejects_unauthorized_binaries(self):
        """Valida que comandos com executores fora da lista permitida são bloqueados."""
        unauthorized = [
            "rm -rf /",
            "bash malicious.sh",
            "sh test.sh",
            "curl https://malicious.com",
            "wget https://malicious.com",
            "powershell Get-Process",
            "cmd.exe /c dir",
            "echo 'hacked'"
        ]

        for cmd in unauthorized:
            with self.assertRaises(ValueError, msg=f"Binário não autorizado não foi bloqueado: {cmd}"):
                test_runner.sanitize_and_validate_test_command(cmd)

    def test_run_distilled_tests_rejects_dangerous_command_without_executing(self):
        """Garante que run_distilled_tests rejeita comandos maliciosos retornando erro seguro."""
        res = test_runner.run_distilled_tests(test_command="rm -rf / && echo 'hacked'")
        self.assertEqual(res["status"], "ERROR")
        error_msg = res.get("error", "") or res.get("summary", "")
        self.assertTrue("segurança" in error_msg.lower() or "não permitido" in error_msg.lower() or "inválido" in error_msg.lower())

    def test_run_distilled_tests_executes_safely_with_shell_false(self):
        """Garante execução segura de comando válido retornando PASS."""
        res = test_runner.run_distilled_tests(test_command="python3 -c \"import sys; sys.exit(0)\"")
        self.assertEqual(res["status"], "PASS")


class TestIssue38Authentication(unittest.TestCase):
    """Validação da camada de autenticação no módulo server/auth.py e FastAPI."""

    def test_auth_module_exists_and_exports_expected_interface(self):
        """Garante que server/auth.py existe e exporta a interface de governança."""
        auth_file = os.path.join(SERVER_DIR, "auth.py")
        self.assertTrue(os.path.exists(auth_file), "Módulo server/auth.py deve existir")

        import auth
        self.assertTrue(hasattr(auth, "AuthManager"), "server/auth.py deve exportar AuthManager")
        self.assertTrue(hasattr(auth, "auth_middleware"), "server/auth.py deve exportar auth_middleware")
        self.assertTrue(hasattr(auth, "verify_ws_auth"), "server/auth.py deve exportar verify_ws_auth")

    def test_auth_manager_standalone_behavior(self):
        """Testa o comportamento de validação e geração de tokens no AuthManager."""
        import auth
        mgr = auth.AuthManager()

        # 1. Com auth desativada
        os.environ["COCKPIT_REQUIRE_AUTH"] = "0"
        os.environ.pop("COCKPIT_AUTH_TOKEN", None)
        self.assertFalse(mgr.is_auth_required())
        self.assertTrue(mgr.verify_token(None))
        self.assertTrue(mgr.verify_token("qualquer_token"))

        # 2. Com token estático via variável de ambiente
        os.environ["COCKPIT_REQUIRE_AUTH"] = "1"
        os.environ["COCKPIT_AUTH_TOKEN"] = "token-secreto-12345"
        self.assertTrue(mgr.is_auth_required())
        self.assertTrue(mgr.verify_token("token-secreto-12345"))
        self.assertFalse(mgr.verify_token("token-invalido"))
        self.assertFalse(mgr.verify_token(None))
        self.assertFalse(mgr.verify_token(""))

        # 3. Com geração automática de token de sessão
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.environ["COCKPIT_REQUIRE_AUTH"] = "1"
            os.environ.pop("COCKPIT_AUTH_TOKEN", None)
            mgr_auto = auth.AuthManager(token_storage_dir=tmp_dir)
            auto_token = mgr_auto.get_or_create_session_token()
            self.assertTrue(len(auto_token) >= 20, "Token gerado deve possuir alta entropia")
            token_file = os.path.join(tmp_dir, "session_token.txt")
            self.assertTrue(os.path.exists(token_file), "session_token.txt deve ser criado")

            self.assertTrue(mgr_auto.verify_token(auto_token))
            self.assertFalse(mgr_auto.verify_token("token-falso"))

        # Limpeza
        os.environ.pop("COCKPIT_REQUIRE_AUTH", None)
        os.environ.pop("COCKPIT_AUTH_TOKEN", None)


class TestIssue38ServerAuthIntegration(unittest.TestCase):
    """Validação da integração de autenticação HTTP e WebSockets no servidor uvicorn."""

    server_thread = None
    server = None
    port = None
    base_url = None
    ws_url = None
    test_token = "valid-test-cockpit-token-999"

    @classmethod
    def setUpClass(cls):
        os.environ["COCKPIT_REQUIRE_AUTH"] = "1"
        os.environ["COCKPIT_AUTH_TOKEN"] = cls.test_token

        import web_server
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.ws_url = f"ws://127.0.0.1:{cls.port}/ws"

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
                data = json.loads(resp.read().decode("utf-8"))
                return resp.getcode(), data
        except urllib.error.HTTPError as e:
            try:
                data = json.loads(e.read().decode("utf-8"))
            except Exception:
                data = {"error": str(e)}
            return e.code, data

    def test_public_routes_accessible_without_token(self):
        """Garante que rotas públicas como /api/health, /api/auth/status e estáticas funcionam sem token."""
        code, data = self._http_get("/api/health")
        self.assertEqual(code, 200)

        code, data = self._http_get("/api/auth/status")
        self.assertEqual(code, 200)
        self.assertTrue(data.get("auth_required"))

        # Rota estática index
        req = urllib.request.Request(f"{self.base_url}/", method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.getcode(), 200)

    def test_protected_routes_reject_unauthorized_requests(self):
        """Garante que rotas /api/* protegidas retornam 401 Unauthorized sem token válido."""
        code, data = self._http_get("/api/state")
        self.assertEqual(code, 401, f"Esperado 401, recebido {code}: {data}")

        code, data = self._http_get("/api/projects")
        self.assertEqual(code, 401)

        code, data = self._http_get("/api/state", headers={"X-Cockpit-Token": "token-falso"})
        self.assertEqual(code, 401)

        code, data = self._http_get("/api/state", headers={"Authorization": "Bearer token-falso"})
        self.assertEqual(code, 401)

    def test_protected_routes_accept_valid_token(self):
        """Garante que rotas protegidas retornam 200 com X-Cockpit-Token ou Bearer token válido."""
        code, data = self._http_get("/api/state", headers={"X-Cockpit-Token": self.test_token})
        self.assertEqual(code, 200)
        self.assertIsInstance(data, dict)

        code, data = self._http_get("/api/projects", headers={"Authorization": f"Bearer {self.test_token}"})
        self.assertEqual(code, 200)
        self.assertIn("projects", data)

    def test_websocket_rejects_unauthorized_connection(self):
        """Garante que conexão WebSocket sem token ou com token inválido é rejeitada com código 1008."""
        async def _test_unauthorized_ws():
            try:
                async with websockets.connect(self.ws_url) as ws:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    self.fail(f"Conexão deveria ser rejeitada, mas recebeu: {msg}")
            except websockets.exceptions.ConnectionClosed as e:
                self.assertEqual(e.code, 1008)
            except Exception as e:
                self.assertIn("1008", str(e))

            bad_ws_url = f"{self.ws_url}?token=token-errado"
            try:
                async with websockets.connect(bad_ws_url) as ws:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    self.fail(f"Conexão com token errado deveria ser rejeitada, mas recebeu: {msg}")
            except websockets.exceptions.ConnectionClosed as e:
                self.assertEqual(e.code, 1008)
            except Exception as e:
                self.assertIn("1008", str(e))

        asyncio.run(_test_unauthorized_ws())

    def test_websocket_accepts_authorized_connection(self):
        """Garante que conexão WebSocket com token válido na query string (?token=...) é aceita."""
        auth_ws_url = f"{self.ws_url}?token={self.test_token}"

        async def _test_authorized_ws():
            async with websockets.connect(auth_ws_url) as ws:
                first_msg_raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                first_msg = json.loads(first_msg_raw)
                self.assertIn(first_msg.get("event"), ["PROJECTS_UPDATED", "STATE_FULL"])

        asyncio.run(_test_authorized_ws())


class TestIssue38ServerAuthDisabledCompatibility(unittest.TestCase):
    """Valida retrocompatibilidade total de HTTP e WebSockets quando autenticação está desativada."""

    server_thread = None
    server = None
    port = None
    base_url = None
    ws_url = None

    @classmethod
    def setUpClass(cls):
        os.environ["COCKPIT_REQUIRE_AUTH"] = "0"
        os.environ.pop("COCKPIT_AUTH_TOKEN", None)

        import web_server
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.ws_url = f"ws://127.0.0.1:{cls.port}/ws"

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

    def _http_get(self, endpoint: str):
        req = urllib.request.Request(f"{self.base_url}{endpoint}", method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.getcode(), data

    def test_http_routes_accessible_without_token_when_auth_disabled(self):
        """Rotas protegidas funcionam sem token quando auth está desativada (padrão retrocompatível)."""
        code, data = self._http_get("/api/state")
        self.assertEqual(code, 200)
        self.assertIsInstance(data, dict)

        code, data = self._http_get("/api/projects")
        self.assertEqual(code, 200)
        self.assertIn("projects", data)

        code, data = self._http_get("/api/auth/status")
        self.assertEqual(code, 200)
        self.assertFalse(data.get("auth_required"))
        self.assertTrue(data.get("authenticated"))

    def test_websocket_connects_without_token_when_auth_disabled(self):
        """Conexão WebSocket aceita sem token quando auth está desativada."""
        async def _test_ws():
            async with websockets.connect(self.ws_url) as ws:
                first_msg_raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                first_msg = json.loads(first_msg_raw)
                self.assertIn(first_msg.get("event"), ["PROJECTS_UPDATED", "STATE_FULL"])

        asyncio.run(_test_ws())


if __name__ == "__main__":
    unittest.main()
