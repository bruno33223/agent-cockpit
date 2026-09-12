import os
import re
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HTML_PATH = os.path.join(REPO_ROOT, "web", "index.html")
CSS_PATH = os.path.join(REPO_ROOT, "web", "styles.css")
JS_PATH = os.path.join(REPO_ROOT, "web", "app.js")


class TestOllamaWebConsole(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            cls.html = f.read()
        with open(CSS_PATH, "r", encoding="utf-8") as f:
            cls.css = f.read()
        with open(JS_PATH, "r", encoding="utf-8") as f:
            cls.js = f.read()

    def test_local_worker_card_process_status_and_buttons(self):
        """Verifica a presença dos elementos no card do Local Worker: status do processo e botões de controle."""
        # 1. Verifica container do card
        self.assertIn('id="local-worker-card"', self.html, "Card local-worker-card ausente no HTML")

        # 2. Verifica status do processo (PID / Executando / Parado)
        self.assertTrue(
            'id="lw-process-status"' in self.html or 'id="lw-proc-status"' in self.html,
            "Indicador de status do processo ausente no card Local Worker"
        )
        self.assertTrue(
            'id="lw-process-pid"' in self.html or 'id="lw-pid"' in self.html,
            "Indicador de PID do processo ausente no card Local Worker"
        )

        # 3. Botões Iniciar Ollama / Parar
        self.assertIn('id="btn-start-ollama"', self.html, "Botão 'Iniciar Ollama' (#btn-start-ollama) ausente no HTML")
        self.assertIn('id="btn-stop-ollama"', self.html, "Botão 'Parar' (#btn-stop-ollama) ausente no HTML")
        self.assertIn("Iniciar Ollama", self.html, "Texto 'Iniciar Ollama' ausente no botão correspondente")
        self.assertIn("Parar", self.html, "Texto 'Parar' ausente no botão correspondente")

        # 4. Botão para abrir Terminal / Console de Logs
        self.assertIn('id="btn-open-ollama-console"', self.html, "Botão '#btn-open-ollama-console' ausente no HTML")
        self.assertTrue(
            "Console de Logs" in self.html or "Terminal de Logs" in self.html,
            "Texto descritivo do botão Console/Terminal de Logs ausente"
        )

    def test_terminal_modal_and_logs_container(self):
        """Verifica a presença do modal/drawer do terminal e container de logs."""
        self.assertTrue(
            'id="modal-ollama-console"' in self.html or 'id="drawer-ollama-console"' in self.html,
            "Modal ou drawer do terminal (#modal-ollama-console) ausente no HTML"
        )
        self.assertIn('id="ollama-terminal-logs"', self.html, "Container de logs (#ollama-terminal-logs) ausente no HTML")
        self.assertIn('id="btn-close-ollama-console"', self.html, "Botão de fechar console (#btn-close-ollama-console) ausente no HTML")

    def test_css_terminal_and_process_styles(self):
        """Verifica estilos CSS para terminal hacker escuro, fonte monospace, auto-scroll e badge de status."""
        # 1. Estilos do terminal de logs
        self.assertIn("ollama-terminal-logs", self.css, "Classe/ID ollama-terminal-logs ausente no CSS")

        # Monospace
        self.assertTrue(
            re.search(r"(\.ollama-terminal-logs|#ollama-terminal-logs)[\s\S]*?font-family:\s*[^;]*monospace", self.css),
            "Fonte monospace ausente para o terminal de logs"
        )

        # Dark theme
        self.assertTrue(
            re.search(r"(\.ollama-terminal-logs|#ollama-terminal-logs)[\s\S]*?background(-color)?:\s*(#[0-9a-fA-F]{3,8}|rgb|rgba)", self.css),
            "Fundo escuro/colorido ausente para o terminal de logs"
        )

        # Auto-scroll / overflow
        self.assertTrue(
            re.search(r"(\.ollama-terminal-logs|#ollama-terminal-logs)[\s\S]*?overflow(-y)?:\s*(auto|scroll)", self.css),
            "Regra de overflow/auto-scroll ausente para o terminal de logs"
        )

        # 2. Badges de status do processo (Executando / Parado)
        self.assertTrue(
            "lw-proc-badge" in self.css or "lw-process-badge" in self.css or "lw-process-status" in self.css,
            "Estilos de badge de status do processo ausentes no CSS"
        )

    def test_js_functions_defined(self):
        """Verifica declaração das funções JavaScript obrigatórias em web/app.js."""
        # Funções esperadas
        self.assertRegex(self.js, r"function\s+startOllamaServer\s*\(", "Função startOllamaServer() não definida em app.js")
        self.assertRegex(self.js, r"function\s+stopOllamaServer\s*\(", "Função stopOllamaServer() não definida em app.js")
        self.assertRegex(self.js, r"function\s+openOllamaConsole\s*\(", "Função openOllamaConsole() não definida em app.js")
        self.assertRegex(self.js, r"function\s+closeOllamaConsole\s*\(", "Função closeOllamaConsole() não definida em app.js")
        self.assertRegex(self.js, r"function\s+renderOllamaLogLine\s*\(", "Função renderOllamaLogLine(line) não definida em app.js")

    def test_js_api_endpoints_invocations(self):
        """Verifica chamadas aos endpoints REST de controle do servidor Ollama e carregamento de logs históricos."""
        self.assertIn("/api/local-worker/start-server", self.js, "Endpoint /api/local-worker/start-server não invocado em app.js")
        self.assertIn("/api/local-worker/stop-server", self.js, "Endpoint /api/local-worker/stop-server não invocado em app.js")
        self.assertIn(
            "/api/local-worker/server-logs",
            self.js,
            "Endpoint formal /api/local-worker/server-logs deve ser invocado para carregamento de logs históricos"
        )

    def test_js_websocket_ollama_log_handling(self):
        """Verifica se mensagens WebSocket com evento 'ollama_log' são devidamente tratadas em app.js."""
        self.assertRegex(
            self.js,
            r"['\"]ollama_log['\"]",
            "Tratamento do evento WebSocket 'ollama_log' ausente em app.js"
        )
        self.assertIn("renderOllamaLogLine", self.js, "renderOllamaLogLine não é chamada no fluxo do app.js")

    def test_js_websocket_ollama_status_and_pid_handling(self):
        """Verifica tratamento do evento WebSocket 'ollama_status' e extração de PID/server_status."""
        self.assertRegex(
            self.js,
            r"['\"]ollama_status['\"]",
            "Tratamento do evento WebSocket 'ollama_status' ausente em app.js"
        )
        self.assertIn(
            "server_status",
            self.js,
            "Extração de metadados do processo a partir de server_status ausente em app.js"
        )


if __name__ == "__main__":
    unittest.main()
