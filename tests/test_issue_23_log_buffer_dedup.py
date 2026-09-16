import os
import re
import subprocess
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOCAL_WORKER_JS_PATH = os.path.join(REPO_ROOT, "web", "js", "local_worker.js")


class TestIssue23LogBufferDedup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(LOCAL_WORKER_JS_PATH, "r", encoding="utf-8") as f:
            cls.js_content = f.read()

    def test_static_code_circular_buffer_limit(self):
        """Verifica se web/js/local_worker.js define limite de 200 linhas e poda FIFO no container de logs."""
        # Deve ter menção ao limite de 200 (ex: MAX_LOG_LINES = 200 ou 200)
        self.assertTrue(
            re.search(r'(MAX_LOG_LINES|MAX_LINES|LOG_BUFFER_LIMIT|200)', self.js_content),
            "Limite máximo de 200 linhas não referenciado no código"
        )
        # Deve ter lógica de poda FIFO verificando se childElementCount excede o limite de 200
        self.assertTrue(
            re.search(r'(childElementCount|children\.length)\s*>\s*(200|MAX_LOG_LINES)', self.js_content)
            or re.search(r'(while|if)\s*\([^)]*(childElementCount|children\.length)[^)]*>\s*(200|MAX_LOG_LINES)', self.js_content),
            "Lógica de verificação de excesso de linhas (childElementCount > 200) não encontrada"
        )
        # Deve remover do topo (FIFO: firstChild, firstElementChild, removeChild ou remove)
        self.assertTrue(
            re.search(r'(firstElementChild|firstChild)\.remove\(\)', self.js_content)
            or re.search(r'removeChild\([^)]*(firstElementChild|firstChild)\)', self.js_content),
            "Remoção FIFO do topo (firstElementChild.remove ou removeChild(firstChild)) não encontrada"
        )

    def test_static_code_deduplication_cache(self):
        """Verifica se existe cache/Set de deduplicação para evitar duplicações entre polling e websocket."""
        # Deve ter um Set de deduplicação declarado em local_worker.js
        self.assertTrue(
            re.search(r'new\s+Set\(', self.js_content),
            "Set de deduplicação não declarado em local_worker.js"
        )
        # Deve checar duplicata antes de renderizar
        self.assertTrue(
            re.search(r'\.(has|includes)\(', self.js_content),
            "Checagem de duplicidade (.has) não encontrada em local_worker.js"
        )

    def test_runtime_circular_buffer_and_dedup_with_node(self):
        """Executa um runner Node.js importando/avaliando renderOllamaLogLine para validar o buffer circular e a deduplicação."""
        node_script = r"""
const fs = require('fs');

// Mock DOM minimalista
class MockElement {
  constructor(id = '', className = '') {
    this.id = id;
    this.className = className;
    this.children = [];
    this.classList = {
      classes: new Set(),
      add: (c) => this.classList.classes.add(c),
      contains: (c) => this.classList.classes.has(c),
      toggle: (c, val) => val ? this.classList.classes.add(c) : this.classList.classes.delete(c)
    };
    this._textContent = '';
  }

  get textContent() {
    if (this.children.length === 0) return this._textContent || '';
    return (this._textContent || '') + this.children.map(c => c.textContent).join('');
  }

  set textContent(val) {
    this._textContent = val;
    this.scrollTop = 0;
    this.scrollHeight = 100;
  }

  get firstElementChild() {
    return this.children[0] || null;
  }

  get firstChild() {
    return this.children[0] || null;
  }

  get childElementCount() {
    return this.children.length;
  }

  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  removeChild(child) {
    const idx = this.children.indexOf(child);
    if (idx !== -1) {
      this.children.splice(idx, 1);
      child.parentElement = null;
    }
    return child;
  }

  remove() {
    if (this.parentElement) {
      this.parentElement.removeChild(this);
    }
  }

  querySelector(sel) {
    if (sel === '.terminal-placeholder') {
      return this.children.find(c => c.className === 'terminal-placeholder' || (c.classList && c.classList.contains('terminal-placeholder'))) || null;
    }
    return null;
  }

  querySelectorAll(sel) {
    if (sel === '.ollama-log-line') {
      return this.children.filter(c => c.className && c.className.includes('ollama-log-line'));
    }
    return [];
  }
}

const terminal = new MockElement('ollama-terminal-logs');
const inpageTerminal = new MockElement('inpage-ollama-logs');
const logCounter = new MockElement('terminal-log-counter');

const elementsMap = {
  'ollama-terminal-logs': terminal,
  'inpage-ollama-logs': inpageTerminal,
  'terminal-log-counter': logCounter
};

global.document = {
  getElementById: (id) => elementsMap[id] || null,
  createElement: (tag) => new MockElement('', '')
};

// Carrega o código do local_worker.js
let code = fs.readFileSync(process.env.LOCAL_WORKER_JS_PATH, 'utf8');

// Remove export / import para execução standalone em Node
code = code.replace(/import\s+[^;]+;/g, '// import removed');
code = code.replace(/export\s+let\s+/g, 'let ');
code = code.replace(/export\s+const\s+/g, 'const ');
code = code.replace(/export\s+async\s+function\s+/g, 'async function ');
code = code.replace(/export\s+function\s+/g, 'function ');

// Executa o script no contexto global
eval(code);

if (typeof renderOllamaLogLine !== 'function') {
  console.error("ERRO: renderOllamaLogLine não é uma função");
  process.exit(1);
}

// 1. TESTE DE BUFFER CIRCULAR: Adicionar 250 linhas
for (let i = 1; i <= 250; i++) {
  renderOllamaLogLine(`Log line ${i}`);
}

if (terminal.childElementCount > 200) {
  console.error(`ERRO_BUFFER_OVERFLOW: esperado <= 200, encontrado ${terminal.childElementCount}`);
  process.exit(2);
}

if (terminal.childElementCount !== 200) {
  console.error(`ERRO_BUFFER_SIZE: esperado exatamente 200 linhas após 250 pushes, encontrado ${terminal.childElementCount}`);
  process.exit(3);
}

// A primeira linha deve ser "Log line 51" (pois 1 a 50 foram podadas pelo FIFO)
const firstLineContent = terminal.children[0].textContent;
if (!firstLineContent.includes('Log line 51')) {
  console.error(`ERRO_FIFO: a primeira linha deveria ser 'Log line 51', mas é: '${firstLineContent}'`);
  process.exit(4);
}

// A última linha deve ser "Log line 250"
const lastLineContent = terminal.children[terminal.children.length - 1].textContent;
if (!lastLineContent.includes('Log line 250')) {
  console.error(`ERRO_FIFO: a última linha deveria ser 'Log line 250', mas é: '${lastLineContent}'`);
  process.exit(5);
}

// 2. TESTE DE DEDUPLICAÇÃO
const countBeforeDedup = terminal.childElementCount;

// Enviar linha idêntica que acabou de ser enviada (como polling e websocket enviando simultâneo)
renderOllamaLogLine('Log line 250');
if (terminal.childElementCount !== countBeforeDedup) {
  console.error(`ERRO_DEDUP: Linha duplicada foi inserida! Linhas antes: ${countBeforeDedup}, agora: ${terminal.childElementCount}`);
  process.exit(6);
}

// Enviar objeto de log duplicado
renderOllamaLogLine({ message: 'Log com timestamp duplicado', timestamp: '12:00:01' });
const countAfterFirstObj = terminal.childElementCount;
renderOllamaLogLine({ message: 'Log com timestamp duplicado', timestamp: '12:00:01' });

if (terminal.childElementCount !== countAfterFirstObj) {
  console.error(`ERRO_DEDUP: Objeto de log idêntico duplicado foi inserido!`);
  process.exit(7);
}

console.log("SUCCESS");
"""
        env = os.environ.copy()
        env["LOCAL_WORKER_JS_PATH"] = LOCAL_WORKER_JS_PATH
        proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, env=env)
        self.assertEqual(
            proc.returncode, 0,
            f"Node test runner falhou (código {proc.returncode}):\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        )


if __name__ == "__main__":
    unittest.main()
