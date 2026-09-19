"""
test_issue_26_chat_batch_synthesis.py: Testes para a Issue #26.
Cobre:
1. Validação do DEFAULT_ZEUS_SYSTEM_PROMPT impondo limite de leitura pontual, limite de ferramentas e obrigatoriedade de síntese final em Markdown para o usuário.
2. Simulação do stream do engine onde ferramentas foram executadas mas nenhum texto de conteúdo útil foi emitido (ou chunks vazios/whitespace), garantindo que o backend injeta uma síntese/resumo antes do evento 'done'.
3. Validação de que se texto já foi emitido pelo modelo, nenhuma síntese automática duplicada é inserida.
4. Validação estática e dinâmica dos handlers frontend em web/js/zeus_chat_workspace.js e web/js/zeus_chat_ui.js garantindo a limpeza e remoção imediata de placeholders de digitação ('typing-indicator', 'thinking-indicator', '⚡ Processando instrução...') no recebimento do evento 'done'.
"""

import os
import sys
import json
import time
import subprocess
import unittest
from unittest.mock import patch, MagicMock

# Configura paths para importação do módulo server
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import zeus_chat_engine
from zeus_chat_engine import (
    DEFAULT_ZEUS_SYSTEM_PROMPT,
    ZeusChatEngine
)


class TestIssue26SystemPrompt(unittest.TestCase):
    """Testa conformidade do prompt do sistema com as restrições da Issue #26."""

    def test_default_system_prompt_has_tool_and_reading_limits_and_mandatory_markdown_synthesis(self):
        """Critério 1: O prompt deve instruir limites de leitura pontual e obrigatoriedade de síntese final em Markdown."""
        prompt = DEFAULT_ZEUS_SYSTEM_PROMPT
        prompt_lower = prompt.lower()

        # Deve conter diretrizes de leitura pontual / evitar ler arquivos inteiros
        self.assertTrue(
            "leitura pontual" in prompt_lower or "buscas pontuais" in prompt_lower,
            "DEFAULT_ZEUS_SYSTEM_PROMPT deve orientar leituras pontuais (grep, head, range) em vez de dumps totais."
        )

        # Deve conter limite de chamadas de ferramentas exploratórias (3 a 5 ou similar)
        self.assertTrue(
            "3 a 5" in prompt or "limite" in prompt_lower,
            "DEFAULT_ZEUS_SYSTEM_PROMPT deve restringir o volume de ferramentas por turno para evitar esgotamento de loop."
        )

        # Deve impor obrigatoriedade de síntese final em Markdown para o usuário
        self.assertTrue(
            "síntese" in prompt_lower or "sintese" in prompt_lower,
            "DEFAULT_ZEUS_SYSTEM_PROMPT deve exigir explicitamente síntese explicativa."
        )
        self.assertTrue(
            "markdown" in prompt_lower,
            "DEFAULT_ZEUS_SYSTEM_PROMPT deve exigir resposta estruturada em Markdown."
        )
        self.assertTrue(
            "obrigatória" in prompt_lower or "obrigatoria" in prompt_lower,
            "DEFAULT_ZEUS_SYSTEM_PROMPT deve especificar que a resposta textual de síntese final é obrigatória."
        )


class TestIssue26BackendBatchSynthesis(unittest.TestCase):
    """Testa detecção e injeção automática de síntese no backend (server/zeus_chat_engine.py)."""

    def setUp(self):
        self.engine = ZeusChatEngine()
        self.session_id = f"test-issue26-{int(time.time()*1000)}"

    def test_backend_injects_synthesis_when_tools_executed_and_zero_text_emitted(self):
        """Critério 2: Quando ferramentas foram executadas mas nenhum texto ('content') foi emitido,
        o backend deve injetar evento de síntese/resumo automático antes do evento 'done'."""
        mock_events = [
            {"type": "tool_call", "tool": "cat", "command": "cat server.py", "output": "file content..."},
            {"type": "tool_call", "tool": "grep", "command": "grep def server.py", "output": "def foo(): pass"},
            {"type": "step_finish", "tokens": {"total": 500}}
        ]

        with patch.object(self.engine, "_stream_opencode", return_value=iter(mock_events)):
            events = list(self.engine.stream_chat(
                session_id=self.session_id,
                message="analise o código e mostre problemas",
                model_id="opencode/default",
                backend="opencode"
            ))

        event_types = [ev["type"] for ev in events]
        self.assertIn("tool_call", event_types)
        self.assertIn("content", event_types, "Deve injetar evento de conteúdo com síntese/resumo automático!")
        self.assertIn("done", event_types)

        # A síntese deve acontecer ANTES do evento 'done'
        content_idx = -1
        done_idx = -1
        for idx, ev in enumerate(events):
            if ev["type"] == "content":
                content_idx = idx
            elif ev["type"] == "done":
                done_idx = idx

        self.assertGreater(done_idx, content_idx, "O evento 'content' de síntese deve ser emitido antes do evento 'done'!")

        # O texto da síntese deve conter a indicação de ações concluídas e resumo das ferramentas
        content_event = events[content_idx]
        synthesis_text = content_event.get("text", "")
        self.assertTrue(
            "As ações e ferramentas solicitadas foram concluídas pelo agente" in synthesis_text
            or "ações e ferramentas foram executadas" in synthesis_text,
            f"Texto de síntese não cumpre o formato esperado: {synthesis_text}"
        )
        # Deve listar ou referenciar as ferramentas chamadas (cat, grep)
        self.assertIn("cat", synthesis_text)
        self.assertIn("grep", synthesis_text)

        # Mensagem persistida no histórico deve conter a síntese
        history = self.engine.session_manager.get_history(self.session_id)
        self.assertTrue(len(history) >= 2)
        assistant_msg = history[-1]
        self.assertEqual(assistant_msg["role"], "assistant")
        self.assertIn(synthesis_text, assistant_msg["content"])

    def test_backend_injects_synthesis_when_only_empty_whitespace_chunks_emitted(self):
        """Critério 2: Se o modelo emitir apenas chunks vazios ou whitespace, ainda deve detectar ausência de síntese real e injetar."""
        mock_events = [
            {"type": "tool_call", "tool": "bash", "command": "ls -la", "output": "total 0"},
            {"type": "content", "text": "   "},
            {"type": "content", "text": ""},
            {"type": "step_finish", "tokens": {"total": 100}}
        ]

        with patch.object(self.engine, "_stream_opencode", return_value=iter(mock_events)):
            events = list(self.engine.stream_chat(
                session_id=self.session_id,
                message="listar diretório",
                model_id="opencode/default",
                backend="opencode"
            ))

        content_events = [ev for ev in events if ev["type"] == "content"]
        texts = [ev.get("text", "") for ev in content_events]
        full_text = "".join(texts)

        self.assertTrue(
            "As ações e ferramentas solicitadas foram concluídas pelo agente" in full_text
            or "ações e ferramentas foram executadas" in full_text,
            "Deve injetar síntese mesmo se apenas whitespace foi emitido antes."
        )

    def test_backend_does_not_inject_duplicate_synthesis_when_model_produced_text(self):
        """Critério c: Se o modelo já produziu texto explicativo legítimo, nenhuma síntese duplicada de fallback deve ser injetada."""
        model_explanation = "Encontrei 2 problemas no arquivo server.py: falta de tratamento de exceção na linha 42 e variável não inicializada."
        mock_events = [
            {"type": "tool_call", "tool": "grep", "command": "grep TODO server.py", "output": "TODO: fix bug"},
            {"type": "content", "text": model_explanation},
            {"type": "step_finish", "tokens": {"total": 450}}
        ]

        with patch.object(self.engine, "_stream_opencode", return_value=iter(mock_events)):
            events = list(self.engine.stream_chat(
                session_id=self.session_id,
                message="analise o código",
                model_id="opencode/default",
                backend="opencode"
            ))

        content_events = [ev for ev in events if ev["type"] == "content"]
        self.assertEqual(len(content_events), 1, "Deve conter unicamente o evento de conteúdo emitido pelo modelo!")
        self.assertEqual(content_events[0].get("text"), model_explanation)
        self.assertNotIn("ações e ferramentas foram executadas pelo motor com sucesso", content_events[0].get("text"))
        self.assertNotIn("As ações e ferramentas solicitadas foram concluídas pelo agente", content_events[0].get("text"))


class TestIssue26FrontendPlaceholderRemoval(unittest.TestCase):
    """Testa remoção imediata de placeholders de digitação no evento 'done' no frontend."""

    @classmethod
    def setUpClass(cls):
        cls.workspace_js_path = os.path.join(BASE_DIR, "web", "js", "zeus_chat_workspace.js")
        cls.ui_js_path = os.path.join(BASE_DIR, "web", "js", "zeus_chat_ui.js")

        with open(cls.workspace_js_path, "r", encoding="utf-8") as f:
            cls.workspace_js = f.read()

        with open(cls.ui_js_path, "r", encoding="utf-8") as f:
            cls.ui_js = f.read()

    def test_workspace_js_cleans_placeholders_immediately_on_done_event(self):
        """Critério 3: web/js/zeus_chat_workspace.js deve remover explicitamente placeholders no bloco event.type === 'done'."""
        done_idx = self.workspace_js.find("event.type === 'done'")
        self.assertNotEqual(done_idx, -1, "Deve existir bloco event.type === 'done' em zeus_chat_workspace.js")
        
        # Pega a janela de código do bloco 'done'
        done_block = self.workspace_js[done_idx:done_idx + 1800]

        # Deve buscar e remover elementos com typing-indicator ou thinking-indicator
        self.assertTrue(
            "typing-indicator" in done_block or "thinking-indicator" in done_block or "typingIndicator" in done_block,
            "zeus_chat_workspace.js deve remover seletores de typing-indicator ou thinking-indicator imediatamente no evento 'done'!"
        )
        self.assertTrue(
            ".remove()" in done_block or "replace" in done_block,
            "zeus_chat_workspace.js deve executar remoção física dos nós de placeholder no evento 'done'!"
        )

    def test_ui_js_cleans_placeholders_immediately_on_done_event(self):
        """Critério 3: web/js/zeus_chat_ui.js deve remover explicitamente placeholders no bloco event.type === 'done'."""
        done_idx = self.ui_js.find("event.type === 'done'")
        self.assertNotEqual(done_idx, -1, "Deve existir bloco event.type === 'done' em zeus_chat_ui.js")

        done_block = self.ui_js[done_idx:done_idx + 1800]

        # Deve buscar e remover elementos com typing-indicator ou thinking-indicator dentro do bloco 'done'
        self.assertTrue(
            "typing-indicator" in done_block or "thinking-indicator" in done_block or "typingIndicator" in done_block,
            "zeus_chat_ui.js deve remover seletores de typing-indicator ou thinking-indicator imediatamente no evento 'done'!"
        )
        self.assertTrue(
            ".remove()" in done_block or "replace" in done_block,
            "zeus_chat_ui.js deve executar remoção física dos nós de placeholder no evento 'done'!"
        )

    def test_node_dynamic_simulation_workspace_placeholder_removal(self):
        """Validação dinâmica em Node.js: simula liveMsg com typing-indicator e verifica se no evento 'done'
        o indicador é 100% removido do DOM."""
        node_script = """
        const fs = require('fs');
        const code = fs.readFileSync('""" + self.workspace_js_path.replace("\\", "/") + """', 'utf8');

        class MockElement {
            constructor(tagName, className = '') {
                this.tagName = tagName.toUpperCase();
                this.className = className;
                this.children = [];
                this.parentNode = null;
                this.style = {};
                this.innerHTML = '';
                this.textContent = '';
                this.classList = {
                    classes: new Set(className ? className.split(' ') : []),
                    add(c) { this.classes.add(c); },
                    remove(c) { this.classes.delete(c); },
                    contains(c) { return this.classes.has(c); }
                };
            }
            appendChild(child) {
                child.parentNode = this;
                this.children.push(child);
                return child;
            }
            remove() {
                if (this.parentNode) {
                    const idx = this.parentNode.children.indexOf(this);
                    if (idx !== -1) this.parentNode.children.splice(idx, 1);
                    this.parentNode = null;
                }
            }
            querySelector(selector) {
                const results = this.querySelectorAll(selector);
                return results.length > 0 ? results[0] : null;
            }
            querySelectorAll(selector) {
                const results = [];
                const parts = selector.split(',').map(s => s.trim());
                const matchNode = (child) => {
                    for (const part of parts) {
                        if (part.startsWith('.') && child.classList.contains(part.slice(1))) return true;
                        if (part.startsWith('#') && child.id === part.slice(1)) return true;
                        if (part.startsWith('[') && part.endsWith(']')) {
                            const attr = part.slice(1, -1).split('=')[0];
                            if (child[attr] !== undefined) return true;
                        }
                    }
                    return false;
                };
                const search = (node) => {
                    for (const child of node.children) {
                        if (matchNode(child)) {
                            results.push(child);
                        }
                        search(child);
                    }
                };
                search(this);
                return results;
            }
        }

        global.document = {
            createElement(tag) { return new MockElement(tag); }
        };
        global.escapeHtml = (s) => s;

        const doneBlockMatch = code.match(/} else if \\(event\\.type === 'done'\\) \\{([\\s\\S]*?)(?:\\} else if|\\}\\s*$)/);
        if (!doneBlockMatch) {
            console.error('Bloco done não encontrado');
            process.exit(1);
        }

        const doneLogic = doneBlockMatch[1];

        const card = new MockElement('div', 'zeus-assistant-card live-streaming');
        const header = new MockElement('div', 'zeus-activity-header');
        const titleSpan = new MockElement('span', 'zeus-activity-title');
        header.appendChild(titleSpan);
        const actTime = new MockElement('span', 'activity-time');
        header.appendChild(actTime);
        card.appendChild(header);

        const body = new MockElement('div', 'zeus-msg-body');
        const typingIndicator = new MockElement('span', 'typing-indicator');
        typingIndicator.textContent = '⚡ Processando instrução...';
        body.appendChild(typingIndicator);
        card.appendChild(body);

        const liveMsg = {
            card,
            activityHeader: header,
            activitySteps: new MockElement('div', 'zeus-activity-steps'),
            body,
            startedContent: true,
            toolsList: [{ tool: 'bash' }]
        };
        const event = { type: 'done', duration_seconds: 2.5, tokens: 120, backend: 'opencode' };
        const elapsed = 2;
        const thisObj = {
            messagesContainer: { scrollTop: 0, scrollHeight: 100 }
        };

        const fn = new Function('liveMsg', 'event', 'elapsed', doneLogic);
        fn.call(thisObj, liveMsg, event, elapsed);

        const remainingTyping = card.querySelectorAll('.typing-indicator');
        const remainingThinking = card.querySelectorAll('.thinking-indicator');
        const hasPlaceholderText = card.innerHTML.includes('Processando instrução') || body.textContent.includes('Processando instrução');

        if (remainingTyping.length > 0 || remainingThinking.length > 0 || hasPlaceholderText) {
            console.error('FALHA: Placeholder de digitação ainda presente após evento done!', {
                remainingTyping: remainingTyping.length,
                remainingThinking: remainingThinking.length,
                hasPlaceholderText
            });
            process.exit(2);
        }

        console.log('SUCESSO: Placeholders completamente removidos no evento done.');
        process.exit(0);
        """
        proc = subprocess.run(
            ["node", "-e", node_script],
            capture_output=True,
            text=True,
            cwd=BASE_DIR
        )
        self.assertEqual(
            proc.returncode, 0,
            f"Validação do workspace falhou no Node.js:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        )

    def test_node_dynamic_simulation_ui_placeholder_removal(self):
        """Validação dinâmica em Node.js: simula liveMsg com typing-indicator em zeus_chat_ui.js
        e verifica se no evento 'done' o indicador é 100% removido do DOM."""
        node_script = """
        const fs = require('fs');
        const code = fs.readFileSync('""" + self.ui_js_path.replace("\\", "/") + """', 'utf8');

        class MockElement {
            constructor(tagName, className = '') {
                this.tagName = tagName.toUpperCase();
                this.className = className;
                this.children = [];
                this.parentNode = null;
                this.style = {};
                this.innerHTML = '';
                this.textContent = '';
                this.classList = {
                    classes: new Set(className ? className.split(' ') : []),
                    add(c) { this.classes.add(c); },
                    remove(c) { this.classes.delete(c); },
                    contains(c) { return this.classes.has(c); }
                };
            }
            appendChild(child) {
                child.parentNode = this;
                this.children.push(child);
                return child;
            }
            remove() {
                if (this.parentNode) {
                    const idx = this.parentNode.children.indexOf(this);
                    if (idx !== -1) this.parentNode.children.splice(idx, 1);
                    this.parentNode = null;
                }
            }
            querySelector(selector) {
                const results = this.querySelectorAll(selector);
                return results.length > 0 ? results[0] : null;
            }
            querySelectorAll(selector) {
                const results = [];
                const parts = selector.split(',').map(s => s.trim());
                const matchNode = (child) => {
                    for (const part of parts) {
                        if (part.startsWith('.') && child.classList.contains(part.slice(1))) return true;
                        if (part.startsWith('#') && child.id === part.slice(1)) return true;
                        if (part.startsWith('[') && part.endsWith(']')) {
                            const attr = part.slice(1, -1).split('=')[0];
                            if (child[attr] !== undefined) return true;
                        }
                    }
                    return false;
                };
                const search = (node) => {
                    for (const child of node.children) {
                        if (matchNode(child)) {
                            results.push(child);
                        }
                        search(child);
                    }
                };
                search(this);
                return results;
            }
        }

        global.document = {
            createElement(tag) { return new MockElement(tag); }
        };
        global.escapeHtml = (s) => s;

        const doneBlockMatch = code.match(/} else if \\(event\\.type === 'done'\\) \\{([\\s\\S]*?)(?:\\} else if|\\}\\s*$)/);
        if (!doneBlockMatch) {
            console.error('Bloco done não encontrado em zeus_chat_ui.js');
            process.exit(1);
        }

        const doneLogic = doneBlockMatch[1];

        const card = new MockElement('div', 'zeus-msg-item live-streaming');
        const header = new MockElement('div', 'zeus-activity-header');
        const actTime = new MockElement('span', 'activity-time');
        header.appendChild(actTime);
        card.appendChild(header);

        const body = new MockElement('div', 'zeus-msg-body');
        const typingIndicator = new MockElement('span', 'typing-indicator');
        typingIndicator.textContent = '⚡ Processando instrução...';
        body.appendChild(typingIndicator);
        card.appendChild(body);

        const liveMsg = {
            card,
            activityHeader: header,
            activitySteps: new MockElement('div', 'zeus-activity-steps'),
            body,
            startedContent: true,
            thinkBox: new MockElement('details'),
            thinkContent: new MockElement('div')
        };
        const event = { type: 'done', duration_seconds: 3.1, tokens: 95, backend: 'opencode' };
        const elapsed = 3;
        const thisObj = {
            messagesContainer: { scrollTop: 0, scrollHeight: 200 }
        };

        const fn = new Function('liveMsg', 'event', 'elapsed', doneLogic);
        fn.call(thisObj, liveMsg, event, elapsed);

        const remainingTyping = card.querySelectorAll('.typing-indicator');
        const remainingThinking = card.querySelectorAll('.thinking-indicator');
        const hasPlaceholderText = card.innerHTML.includes('Processando instrução') || body.textContent.includes('Processando instrução');

        if (remainingTyping.length > 0 || remainingThinking.length > 0 || hasPlaceholderText) {
            console.error('FALHA: Placeholder de digitação ainda presente no UI após evento done!', {
                remainingTyping: remainingTyping.length,
                remainingThinking: remainingThinking.length,
                hasPlaceholderText
            });
            process.exit(2);
        }

        console.log('SUCESSO: Placeholders de UI completamente removidos no evento done.');
        process.exit(0);
        """
        proc = subprocess.run(
            ["node", "-e", node_script],
            capture_output=True,
            text=True,
            cwd=BASE_DIR
        )
        self.assertEqual(
            proc.returncode, 0,
            f"Validação do UI falhou no Node.js:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        )


if __name__ == "__main__":
    unittest.main()

