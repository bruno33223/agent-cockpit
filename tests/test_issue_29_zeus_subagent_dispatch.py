"""
tests/test_issue_29_zeus_subagent_dispatch.py: Testes automatizados para a Issue #29:
[Orquestrador Zeus] Decomposição autônoma e despacho de subagentes para tarefas complexas.

Cobre:
1. Presença de regras de escopo e despacho autônomo no DEFAULT_ZEUS_SYSTEM_PROMPT.
2. Definição do schema OpenAI function de subagent_spawn no catálogo AVAILABLE_TOOLS do engine.
3. Injeção de AVAILABLE_TOOLS no payload de provedores (OmniRoute e Ollama).
4. Execução simulada com emissão de evento SSE subagent_spawn completo (slice_id, role, task, target_files, worktree_path) sem fechar a sessão principal.
5. Integração da fatia com Git Worktree e sessão de terminal PTY dedicada.
6. Tratamento de subagent_spawn e renderização de feedback visual nos arquivos frontend.
"""

import os
import sys
import json
import time
import uuid
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

# Adiciona o diretório server ao path
SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import zeus_chat_engine
from zeus_chat_engine import (
    zeus_engine,
    ZeusChatEngine,
    DEFAULT_ZEUS_SYSTEM_PROMPT
)


class TestZeusSubagentDispatchPromptAndTools(unittest.TestCase):
    """Validação de diretrizes de orquestração e schemas de ferramentas no engine."""

    def test_default_zeus_system_prompt_autonomous_dispatch_rules(self):
        """Critério 1: DEFAULT_ZEUS_SYSTEM_PROMPT deve forçar avaliação de escopo e uso de subagent_spawn."""
        prompt = DEFAULT_ZEUS_SYSTEM_PROMPT
        
        # Deve instruir sobre avaliação de escopo antes de executar
        self.assertIn("escopo", prompt.lower(), "O prompt deve mencionar avaliação de escopo.")
        
        # Deve orientar explicitamente que tarefas multi-arquivo / complexas exigem subagentes
        self.assertTrue(
            "múltiplos arquivos" in prompt.lower() or "multi-arquivo" in prompt.lower() or "multiplos arquivos" in prompt.lower(),
            "O prompt deve orientar sobre tarefas que afetam múltiplos arquivos."
        )
        
        # Deve citar explicitamente a ferramenta subagent_spawn
        self.assertIn("subagent_spawn", prompt, "O prompt deve citar a ferramenta subagent_spawn para delegação.")
        
        # Deve instruir contra execução monolítica no chat principal
        self.assertTrue(
            "monolítica" in prompt.lower() or "sequencial" in prompt.lower() or "diretamente no chat" in prompt.lower() or "sem delegar" in prompt.lower(),
            "O prompt deve proibir execução monolítica direta no chat principal para tarefas complexas."
        )
        
        # Deve instruir os parâmetros essenciais: slice_id, role, task, target_files
        self.assertIn("slice_id", prompt, "O prompt deve citar o parâmetro slice_id.")
        self.assertIn("role", prompt, "O prompt deve citar o parâmetro role (builder ou critic).")

    def test_available_tools_schema_definition(self):
        """Critério 2: AVAILABLE_TOOLS deve ser definido com o schema da ferramenta subagent_spawn."""
        self.assertTrue(
            hasattr(zeus_chat_engine, "AVAILABLE_TOOLS"),
            "AVAILABLE_TOOLS deve estar definido no módulo zeus_chat_engine."
        )
        tools = getattr(zeus_chat_engine, "AVAILABLE_TOOLS", [])
        self.assertIsInstance(tools, list, "AVAILABLE_TOOLS deve ser uma lista.")
        
        # Procura a definição de subagent_spawn
        spawn_tool = next(
            (t for t in tools if (isinstance(t, dict) and t.get("function", {}).get("name") == "subagent_spawn")),
            None
        )
        self.assertIsNotNone(spawn_tool, "A ferramenta 'subagent_spawn' deve existir em AVAILABLE_TOOLS.")
        
        fn = spawn_tool.get("function", {})
        self.assertEqual(fn.get("name"), "subagent_spawn")
        self.assertTrue(len(fn.get("description", "")) > 20, "subagent_spawn deve ter documentação descritiva.")
        
        params = fn.get("parameters", {})
        self.assertEqual(params.get("type"), "object")
        props = params.get("properties", {})
        
        # Campos obrigatórios e tipados
        self.assertIn("slice_id", props, "slice_id deve constar nos parâmetros.")
        self.assertEqual(props["slice_id"].get("type"), "string")
        
        self.assertIn("task", props, "task deve constar nos parâmetros.")
        self.assertEqual(props["task"].get("type"), "string")
        
        self.assertIn("role", props, "role deve constar nos parâmetros.")
        self.assertEqual(props["role"].get("type"), "string")
        
        self.assertIn("target_files", props, "target_files deve constar nos parâmetros.")
        self.assertEqual(props["target_files"].get("type"), "array")
        
        self.assertIn("worktree_path", props, "worktree_path deve constar nos parâmetros.")
        self.assertEqual(props["worktree_path"].get("type"), "string")
        
        required = params.get("required", [])
        for field in ["slice_id", "task", "role"]:
            self.assertIn(field, required, f"Campo '{field}' deve ser obrigatório.")

    def test_tools_passed_to_omniroute_and_ollama_payloads(self):
        """Critério 2: As ferramentas devem ser injetadas nos payloads dos provedores de inferência."""
        engine = ZeusChatEngine()
        tools = getattr(zeus_chat_engine, "AVAILABLE_TOOLS", None)
        self.assertIsNotNone(tools, "AVAILABLE_TOOLS deve existir.")

        # Verifica injeção no payload do OmniRoute
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = [
                b'data: {"choices":[{"delta":{"content":"OK"}}]}\n\n',
                b'data: [DONE]\n\n'
            ]
            mock_urlopen.return_value = mock_resp

            # Consome o gerador
            list(engine._stream_omniroute(
                session_id="test-session-tools",
                message="Decomponha a tarefa",
                model_id="gpt-4o"
            ))

            self.assertTrue(mock_urlopen.called)
            req = mock_urlopen.call_args[0][0]
            payload = json.loads(req.data.decode("utf-8"))
            self.assertIn("tools", payload, "Payload para OmniRoute deve conter o atributo 'tools'.")
            self.assertEqual(payload["tools"], tools, "As ferramentas passadas devem corresponder a AVAILABLE_TOOLS.")

        # Verifica injeção no payload do Ollama
        with patch("urllib.request.urlopen") as mock_urlopen_ollama:
            mock_resp_ollama = MagicMock()
            mock_resp_ollama.__enter__.return_value = [
                b'{"message":{"content":"OK"}}\n'
            ]
            mock_urlopen_ollama.return_value = mock_resp_ollama

            list(engine._stream_ollama(
                session_id="test-session-ollama",
                message="Decomponha a tarefa",
                model_id="qwen2.5-coder:7b"
            ))

            self.assertTrue(mock_urlopen_ollama.called)
            req_ollama = mock_urlopen_ollama.call_args[0][0]
            payload_ollama = json.loads(req_ollama.data.decode("utf-8"))
            self.assertIn("tools", payload_ollama, "Payload para Ollama deve conter o atributo 'tools'.")
            self.assertEqual(payload_ollama["tools"], tools, "As ferramentas passadas ao Ollama devem ser AVAILABLE_TOOLS.")


class TestZeusSubagentDispatchExecution(unittest.TestCase):
    """Validação do ciclo de vida de execução de subagent_spawn via streaming SSE."""

    def test_subagent_spawn_event_emission_with_rich_metadata(self):
        """Critério 2 & 3: Chamada a subagent_spawn deve gerar evento SSE completo sem fechar a sessão do chat."""
        engine = ZeusChatEngine()
        session_id = f"session-{uuid.uuid4().hex[:8]}"

        fake_tool_call = {
            "id": "call-spawn-123",
            "type": "function",
            "function": {
                "name": "subagent_spawn",
                "arguments": json.dumps({
                    "slice_id": "slice-auth-jwt",
                    "role": "builder",
                    "task": "Implementar middleware de autenticação JWT e testes de integração",
                    "target_files": ["server/auth.py", "tests/test_auth.py"],
                    "worktree_path": ".worktrees/slice-auth-jwt"
                })
            }
        }

        # Simula resposta do OmniRoute emitindo raciocínio, tool_call de subagent_spawn e síntese final
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = [
                b'data: {"choices":[{"delta":{"thinking":"Planejando decomposicao da tarefa..."}}]}\n\n',
                f'data: {{"choices":[{{"delta":{{"tool_calls":[{json.dumps(fake_tool_call)}]}}}}]}}\n\n'.encode("utf-8"),
                b'data: {"choices":[{"delta":{"content":"Subagente builder despachado com sucesso para a fatia slice-auth-jwt."}}]}\n\n',
                b'data: [DONE]\n\n'
            ]
            mock_urlopen.return_value = mock_resp

            events = list(engine.stream_chat(
                session_id=session_id,
                message="Implemente autenticacao JWT no sistema",
                backend="omniroute",
                model_id="gpt-4o"
            ))

            event_types = [ev["type"] for ev in events]
            self.assertIn("subagent_spawn", event_types, "Deve emitir evento de tipo 'subagent_spawn'.")
            self.assertIn("content", event_types, "Deve emitir evento de tipo 'content'.")
            self.assertIn("done", event_types, "Deve emitir evento 'done' de conclusão da sessão.")

            # Encontra o evento de spawn
            spawn_ev = next(ev for ev in events if ev["type"] == "subagent_spawn")
            self.assertEqual(spawn_ev.get("slice_id"), "slice-auth-jwt")
            self.assertEqual(spawn_ev.get("role"), "builder")
            self.assertEqual(spawn_ev.get("task"), "Implementar middleware de autenticação JWT e testes de integração")
            self.assertEqual(spawn_ev.get("target_files"), ["server/auth.py", "tests/test_auth.py"])
            self.assertEqual(spawn_ev.get("worktree_path"), ".worktrees/slice-auth-jwt")

            # Verifica histórico da sessão: não pode estar vazio nem fechado
            history = engine.get_history(session_id)
            self.assertEqual(len(history), 2)  # Mensagem do usuário + assistente
            assistant_msg = history[-1]
            self.assertEqual(assistant_msg["role"], "assistant")
            self.assertIsNotNone(assistant_msg.get("subagents"))
            self.assertEqual(len(assistant_msg["subagents"]), 1)
            self.assertEqual(assistant_msg["subagents"][0]["slice_id"], "slice-auth-jwt")

    def test_fallback_engine_multi_file_autonomous_decomposition(self):
        """Critério 1: Motor de fallback local decompõe demandas multi-arquivo com subagent_spawn rico."""
        engine = ZeusChatEngine()
        session_id = f"session-fallback-{uuid.uuid4().hex[:8]}"

        events = list(engine.stream_chat(
            session_id=session_id,
            message="Criar novo subsistema multi-arquivo de faturamento com banco de dados e rotas",
            backend="fallback"
        ))

        event_types = [ev["type"] for ev in events]
        self.assertIn("subagent_spawn", event_types, "Fallback deve emitir subagent_spawn para tarefa complexa.")

        spawn_ev = next(ev for ev in events if ev["type"] == "subagent_spawn")
        self.assertTrue(spawn_ev.get("slice_id"), "Deve possuir slice_id estruturado.")
        self.assertTrue(spawn_ev.get("role"), "Deve possuir role estruturado.")
        self.assertTrue(spawn_ev.get("task"), "Deve possuir task descritiva.")
        self.assertTrue(isinstance(spawn_ev.get("target_files"), list), "target_files deve ser uma lista.")


class TestZeusSubagentWorktreeAndTerminalIntegration(unittest.TestCase):
    """Validação da integração não destrutiva entre fatia, Git Worktree e terminal PTY."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_cockpit_worktree_")
        # Inicializa um repositório git temporário
        import subprocess
        subprocess.run(["git", "init"], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@cockpit.local"], cwd=self.test_dir, check=True, capture_output=True)
        
        # Cria commit inicial
        readme = os.path.join(self.test_dir, "README.md")
        with open(readme, "w") as f:
            f.write("# Cockpit Test Repo\n")
        subprocess.run(["git", "add", "README.md"], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=self.test_dir, check=True, capture_output=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_worktree_allocation_and_pty_session_association(self):
        """Critério 3: Despacho de fatia aloca worktree isolado e associa sessão PTY mantendo chat principal ativo."""
        from server.git_worktrees import create_slice_worktree
        from server.pty_manager import PTYSessionManager

        slice_id = "slice-29-billing"
        res = create_slice_worktree(slice_id=slice_id, repo_root=self.test_dir)
        self.assertEqual(res.get("status"), "CREATED")
        worktree_path = res.get("worktree_path")
        self.assertTrue(os.path.isdir(worktree_path), f"Diretório do worktree deve existir: {worktree_path}")

        # Cria sessão PTY apontando para o worktree isolado
        pty_mgr = PTYSessionManager()
        term_session = pty_mgr.get_or_create(
            session_id=f"term-{slice_id}",
            cwd=worktree_path,
            project_id="test-proj",
            role="builder",
            slice_id=slice_id,
            name=f"Builder [{slice_id}]"
        )
        self.assertIsNotNone(term_session)
        self.assertEqual(term_session.slice_id, slice_id)
        self.assertEqual(os.path.realpath(term_session.cwd), os.path.realpath(worktree_path))
        self.assertEqual(term_session.role, "builder")


class TestFrontendSubagentVisualFeedback(unittest.TestCase):
    """Validação da presença de tratamento de subagent_spawn e feedback visual no frontend."""

    def test_frontend_workspace_js_handles_target_files_and_worktree(self):
        """Critério 2 & 3: zeus_chat_workspace.js deve tratar target_files e worktree_path no card do subagente."""
        workspace_js_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web", "js", "zeus_chat_workspace.js"))
        self.assertTrue(os.path.isfile(workspace_js_path), "zeus_chat_workspace.js deve existir.")
        
        with open(workspace_js_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("handleSubagentSpawn", content)
        self.assertIn("btn-open-subagent-terminal", content)
        # Deve ter suporte aos novos metadados da Issue #29
        self.assertTrue(
            "target_files" in content or "targetFiles" in content,
            "zeus_chat_workspace.js deve referenciar target_files/targetFiles."
        )

    def test_frontend_ui_js_handles_subagent_spawn_event(self):
        """Critério 2 & 3: zeus_chat_ui.js deve possuir manipulador para o evento subagent_spawn."""
        ui_js_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web", "js", "zeus_chat_ui.js"))
        self.assertTrue(os.path.isfile(ui_js_path), "zeus_chat_ui.js deve existir.")
        
        with open(ui_js_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("subagent_spawn", content, "zeus_chat_ui.js deve manipular evento 'subagent_spawn'.")


if __name__ == "__main__":
    unittest.main()
