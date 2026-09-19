"""
tests/test_issue_40_chat_rehydration_and_hf_hub.py

Testes automatizados para Issue #40:
[Frontend & UX] Reidratação de histórico do Zeus Chat no reload (F5) e atalho para Hugging Face Hub
- (a) Implementação no ZeusChatCore / ZeusChatSessionController do método de carga de histórico
- (b) Persistência e leitura do sessionId via localStorage e supressão da mensagem de boas-vindas
- (c) Renderização/reidratação de mensagens recuperadas do histórico (balões user e assistant)
- (d) Presença do card em destaque do Hugging Face Hub em web/index.html com botão de atalho
- (e) Integração em web/js/local_worker.js para abertura do modal e foco no campo de busca do HF Hub
- (f) Validação funcional com o endpoint real da API /api/zeus-chat/session/{session_id}/history
"""

import os
import sys
import json
import uuid
import unittest
import subprocess

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_DIR = os.path.join(REPO_ROOT, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

CHAT_CORE_JS = os.path.join(REPO_ROOT, "web", "js", "chat", "zeus_chat_core.js")
WORKSPACE_JS = os.path.join(REPO_ROOT, "web", "js", "zeus_chat_workspace.js")
LOCAL_WORKER_JS = os.path.join(REPO_ROOT, "web", "js", "local_worker.js")
INDEX_HTML = os.path.join(REPO_ROOT, "web", "index.html")


class TestIssue40ChatRehydrationAndHfHub(unittest.TestCase):
    """Bateria de testes TDD para a Issue #40."""

    def test_a_load_history_method_implementation(self):
        """Critério 1 (a): ZeusChatCore e ZeusChatSessionController devem implementar loadHistory / fetchHistory chamando a API."""
        with open(CHAT_CORE_JS, "r", encoding="utf-8") as f:
            core_code = f.read()

        self.assertTrue(
            "loadHistory" in core_code or "fetchHistory" in core_code,
            "ZeusChatCore deve implementar o método loadHistory ou fetchHistory"
        )
        self.assertIn(
            "/api/zeus-chat/session/",
            core_code,
            "ZeusChatCore deve consultar a rota /api/zeus-chat/session/{session_id}/history"
        )
        self.assertIn(
            "/history",
            core_code,
            "ZeusChatCore deve apontar para o endpoint de histórico"
        )

        with open(WORKSPACE_JS, "r", encoding="utf-8") as f:
            ws_code = f.read()

        self.assertTrue(
            "loadHistory" in ws_code or "fetchHistory" in ws_code,
            "ZeusChatSessionController deve conter método loadHistory ou fetchHistory"
        )

        # Validação dinâmica em Node.js simulado
        node_script = f"""
        const fs = require('fs');
        const vm = require('vm');

        let coreContent = fs.readFileSync('{CHAT_CORE_JS}', 'utf-8');
        coreContent = coreContent.replace(/export\\s+class\\s+/g, 'class ');
        coreContent = coreContent.replace(/export\\s+const\\s+/g, 'const ');
        coreContent = coreContent.replace(/import\\s+.*?from\\s+.*?;/g, '');

        const context = {{
            window: {{}},
            console: console,
            fetch: async (url) => {{
                return {{
                    ok: true,
                    json: async () => ({{ status: 'ok', session_id: 'test-sess', history: [{{ id: '1', role: 'user', content: 'test' }}] }})
                }};
            }}
        }};
        vm.createContext(context);
        vm.runInContext(coreContent, context);

        const CoreClass = context.ZeusChatCore || context.window?.ZeusChatCore;
        if (!CoreClass) {{
            console.error('ZeusChatCore não encontrado no contexto');
            process.exit(1);
        }}
        const core = new CoreClass();
        const fetchMethod = core.loadHistory || core.fetchHistory;
        if (typeof fetchMethod !== 'function') {{
            console.error('loadHistory/fetchHistory is not a function');
            process.exit(1);
        }}

        fetchMethod.call(core, 'test-sess', async (url) => {{
            if (!url.includes('/api/zeus-chat/session/test-sess/history')) {{
                console.error('URL incorreta:', url);
                process.exit(2);
            }}
            return {{
                ok: true,
                json: async () => ({{ status: 'ok', session_id: 'test-sess', history: [{{ id: '1', role: 'user', content: 'test' }}] }})
            }};
        }}).then(res => {{
            if (!Array.isArray(res) || res.length !== 1 || res[0].content !== 'test') {{
                console.error('Retorno inválido:', res);
                process.exit(3);
            }}
            process.exit(0);
        }}).catch(err => {{
            console.error(err);
            process.exit(4);
        }});
        """
        proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
        self.assertEqual(
            proc.returncode,
            0,
            f"Falha na validação Node do método loadHistory em ZeusChatCore:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        )

    def test_b_localstorage_session_persistence_and_welcome_suppression(self):
        """Critério 1 (b): Persistência de sessionId no localStorage (chave 'zeus_chat_active_session_id') e supressão da mensagem de boas-vindas."""
        with open(WORKSPACE_JS, "r", encoding="utf-8") as f:
            ws_code = f.read()

        self.assertIn(
            "zeus_chat_active_session_id",
            ws_code,
            "zeus_chat_workspace.js deve persistir e ler a chave 'zeus_chat_active_session_id' no localStorage"
        )
        self.assertIn(
            "localStorage",
            ws_code,
            "zeus_chat_workspace.js deve interagir com localStorage"
        )

        node_script = f"""
        const fs = require('fs');
        const code = fs.readFileSync('{WORKSPACE_JS}', 'utf-8');
        if (!code.includes('zeus_chat_active_session_id')) {{
            console.error('Falta zeus_chat_active_session_id');
            process.exit(1);
        }}
        process.exit(0);
        """
        proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
        self.assertEqual(
            proc.returncode,
            0,
            f"Falha na validação de persistência no localStorage:\n{proc.stderr}"
        )

    def test_c_history_messages_rendering_and_rehydration(self):
        """Critério 1 (c): Renderização e reidratação de mensagens (user e assistant) com thinking e timestamp."""
        node_script = f"""
        const fs = require('fs');
        const vm = require('vm');

        let mrCode = fs.readFileSync('{os.path.join(REPO_ROOT, "web", "js", "chat", "message_renderer.js")}', 'utf-8');
        mrCode = mrCode.replace(/export\\s+const\\s+/g, 'var ');
        mrCode = mrCode.replace(/export\\s+class\\s+/g, 'class ');
        mrCode = mrCode.replace(/import\\s+.*?from\\s+.*?;/g, '');

        let subCardCode = fs.readFileSync('{os.path.join(REPO_ROOT, "web", "js", "chat", "subagent_card_renderer.js")}', 'utf-8');
        subCardCode = subCardCode.replace(/const\\s+safeEscapeHtml/g, 'var safeEscapeHtml');
        subCardCode = subCardCode.replace(/export\\s+const\\s+/g, 'var ');
        subCardCode = subCardCode.replace(/export\\s+class\\s+/g, 'class ');
        subCardCode = subCardCode.replace(/import\\s+.*?from\\s+.*?;/g, '');

        let coreCode = fs.readFileSync('{CHAT_CORE_JS}', 'utf-8');
        coreCode = coreCode.replace(/export\\s+const\\s+/g, 'const ');
        coreCode = coreCode.replace(/export\\s+class\\s+/g, 'class ');
        coreCode = coreCode.replace(/import\\s+.*?from\\s+.*?;/g, '');

        let wsCode = fs.readFileSync('{WORKSPACE_JS}', 'utf-8');
        wsCode = wsCode.replace(/export\\s+const\\s+/g, 'const ');
        wsCode = wsCode.replace(/export\\s+class\\s+/g, 'class ');
        wsCode = wsCode.replace(/export\\s+function\\s+/g, 'function ');
        wsCode = wsCode.replace(/import\\s+.*?from\\s+.*?;/g, '');

        const storage = new Map();
        storage.set('zeus_chat_active_session_id', 'rehydrate-session-42');

        const mockContainer = {{
            children: [],
            innerHTML: '',
            scrollTop: 0,
            scrollHeight: 100,
            appendChild(c) {{ this.children.push(c); return c; }}
        }};

        const mockPane = {{
            querySelector(sel) {{
                if (sel.includes('messages')) return mockContainer;
                return {{ addEventListener: () => {{}}, style: {{}} }};
            }},
            querySelectorAll(sel) {{ return []; }}
        }};

        const mockHistory = [
            {{ id: 'm1', role: 'user', content: 'Explique a Issue #40', timestamp: 1710000000 }},
            {{ id: 'm2', role: 'assistant', content: 'A Issue #40 resolve a reidratação.', thinking: 'Refletindo sobre a arquitetura...', timestamp: 1710000005 }}
        ];

        const context = {{
            window: {{}},
            document: {{
                createElement(tag) {{
                    const el = {{
                        tagName: tag.toUpperCase(),
                        className: '',
                        innerHTML: '',
                        textContent: '',
                        style: {{}},
                        children: [],
                        appendChild(c) {{ this.children.push(c); return c; }},
                        querySelector(s) {{
                            if (s.includes('steps') || s.includes('tools')) return {{ appendChild: (x) => el.children.push(x) }};
                            return null;
                        }},
                        querySelectorAll: () => []
                    }};
                    return el;
                }}
            }},
            localStorage: {{
                getItem: (k) => storage.get(k) || null,
                setItem: (k, v) => storage.set(k, String(v)),
                removeItem: (k) => storage.delete(k)
            }},
            fetch: async (url) => {{
                if (url.includes('/api/zeus-chat/session/rehydrate-session-42/history')) {{
                    return {{
                        ok: true,
                        json: async () => ({{ status: 'ok', session_id: 'rehydrate-session-42', history: mockHistory }})
                    }};
                }}
                return {{ ok: false, json: async () => ({{ error: 'Not found' }}) }};
            }},
            console: console,
            setTimeout: (fn) => fn(),
            escapeHtml: (s) => (s || '')
        }};

        vm.createContext(context);
        vm.runInContext(mrCode, context);
        vm.runInContext(subCardCode, context);
        vm.runInContext(coreCode, context);
        vm.runInContext(wsCode, context);

        const CtrlClass = context.ZeusChatSessionController || context.window?.ZeusChatSessionController;
        if (!CtrlClass) {{
            console.error('ZeusChatSessionController não encontrado no contexto');
            process.exit(1);
        }}
        const ctrl = new CtrlClass(null, mockPane);

        (async () => {{
            if (typeof ctrl.loadHistory === 'function') {{
                await ctrl.loadHistory('rehydrate-session-42');
            }} else if (typeof ctrl.fetchHistory === 'function') {{
                await ctrl.fetchHistory('rehydrate-session-42');
            }} else {{
                console.error('Controlador não possui loadHistory nem fetchHistory');
                process.exit(1);
            }}

            if (ctrl.messages.length < 2) {{
                console.error('Mensagens não foram reidratadas:', ctrl.messages);
                process.exit(2);
            }}

            const hasUser = ctrl.messages.some(m => m.role === 'user' && m.content.includes('Issue #40'));
            const hasAssistant = ctrl.messages.some(m => m.role === 'assistant' && m.content.includes('reidratação'));
            if (!hasUser || !hasAssistant) {{
                console.error('Mensagens reidratadas incompletas:', ctrl.messages);
                process.exit(3);
            }}

            const hasWelcome = ctrl.messages.some(m => m.content && m.content.includes('Zeus Master Chat Online'));
            if (hasWelcome) {{
                console.error('Mensagem de boas-vindas não foi suprimida durante a reidratação:', ctrl.messages);
                process.exit(4);
            }}

            process.exit(0);
        }})().catch(err => {{
            console.error('Erro na reidratação:', err);
            process.exit(5);
        }});
        """
        proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
        self.assertEqual(
            proc.returncode,
            0,
            f"Falha na reidratação de histórico:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        )

    def test_d_hf_hub_shortcut_card_in_index_html(self):
        """Critério 2 (d): Presença do card em destaque do Hugging Face Hub em web/index.html com botão de atalho."""
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            html = f.read()

        self.assertTrue(
            'id="card-hf-hub-shortcut"' in html or 'class="worker-grid-card hf-hub-shortcut-card"' in html or 'hf-hub-shortcut-card' in html,
            "web/index.html deve conter o card de atalho para o Hugging Face Hub (id='card-hf-hub-shortcut')"
        )
        self.assertIn(
            "Hugging Face Hub",
            html,
            "web/index.html deve mencionar claramente 'Hugging Face Hub'"
        )
        self.assertIn(
            "GGUF",
            html,
            "web/index.html deve indicar suporte a modelos GGUF da comunidade"
        )
        self.assertTrue(
            'id="btn-open-hf-hub"' in html or 'btn-open-pull-modal' in html,
            "web/index.html deve conter o botão de atalho para abertura da busca do HF Hub ('btn-open-hf-hub')"
        )

    def test_e_hf_hub_shortcut_integration_in_local_worker_js(self):
        """Critério 2 (e): Integração em web/js/local_worker.js para abertura do modal e foco no campo de busca do HF Hub."""
        with open(LOCAL_WORKER_JS, "r", encoding="utf-8") as f:
            lw_code = f.read()

        self.assertTrue(
            "btn-open-hf-hub" in lw_code or "btnOpenHfHub" in lw_code or "openHfHubShortcut" in lw_code,
            "local_worker.js deve referenciar o botão de atalho do Hugging Face Hub ('btn-open-hf-hub')"
        )
        self.assertTrue(
            "modal-model-download" in lw_code or "openModelModal" in lw_code,
            "local_worker.js deve abrir o modal de modelos ao acionar o atalho"
        )
        self.assertTrue(
            "hf-search-input" in lw_code or "inputHfSearch" in lw_code,
            "local_worker.js deve focar ou apontar para o campo de busca do Hugging Face Hub"
        )
        self.assertTrue(
            "hf-hub-section" in lw_code or "scrollIntoView" in lw_code or "focus" in lw_code,
            "local_worker.js deve direcionar o foco ou rolar até a seção do Hugging Face Hub"
        )

    def test_f_backend_api_history_endpoint_validation(self):
        """Critério 1 (f): Validação funcional com o endpoint real da API /api/zeus-chat/session/{session_id}/history."""
        from server.routers.zeus_chat import get_zeus_chat_history_endpoint, delete_zeus_chat_session_endpoint, zeus_chat_engine

        self.assertIsNotNone(zeus_chat_engine, "zeus_chat_engine deve estar disponível no router")
        session_id = f"test-issue-40-{uuid.uuid4().hex[:8]}"

        # 1. Popula mensagens no histórico via session_manager do engine
        msg1 = zeus_chat_engine.zeus_engine.session_manager.append_message(
            session_id=session_id,
            role="user",
            content="Olá Zeus, testando Issue #40."
        )
        msg2 = zeus_chat_engine.zeus_engine.session_manager.append_message(
            session_id=session_id,
            role="assistant",
            content="Perfeito! Histórico gravado com sucesso.",
            thinking="Pensamento de auditoria TDD..."
        )

        # 2. Chama endpoint de histórico
        resp = get_zeus_chat_history_endpoint(session_id)
        self.assertEqual(resp.get("status"), "ok")
        self.assertEqual(resp.get("session_id"), session_id)
        self.assertEqual(resp.get("count"), 2)

        history = resp.get("history", [])
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["content"], "Olá Zeus, testando Issue #40.")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertEqual(history[1]["content"], "Perfeito! Histórico gravado com sucesso.")
        self.assertEqual(history[1]["thinking"], "Pensamento de auditoria TDD...")

        # 3. Deleta sessão e valida limpeza
        del_resp = delete_zeus_chat_session_endpoint(session_id)
        self.assertEqual(del_resp.get("status"), "ok")
        self.assertTrue(del_resp.get("deleted"))

        # 4. Histórico subsequente deve retornar vazio
        empty_resp = get_zeus_chat_history_endpoint(session_id)
        self.assertEqual(empty_resp.get("count"), 0)
        self.assertEqual(empty_resp.get("history"), [])


if __name__ == "__main__":
    unittest.main()
