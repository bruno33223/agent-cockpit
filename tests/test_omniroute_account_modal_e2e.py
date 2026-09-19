import os
import sys
import json
import time
import socket
import asyncio
import unittest
import subprocess
import urllib.request
import websockets

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestOmniRouteAccountModalE2E(unittest.TestCase):
    """
    Testes Ponta a Ponta (E2E) para a interface do OmniRoute na tela de Configurações:
    - Validação de hierarquia e Z-Index no CSS (o modal da conta DEVE sobrepor o modal de configurações)
    - Validação de estrutura HTML e IDs essenciais
    - Validação lógica e listeners em settings.js
    - Teste real com Headless Google Chrome via CDP (Chrome DevTools Protocol)
    """

    chrome_proc = None
    cdp_port = None
    ws_url = None

    @classmethod
    def setUpClass(cls):
        # 1. Verifica caminhos dos arquivos
        cls.html_path = os.path.join(BASE_DIR, 'web', 'index.html')
        cls.modals_css_path = os.path.join(BASE_DIR, 'web', 'css', 'modals.css')
        cls.styles_css_path = os.path.join(BASE_DIR, 'web', 'styles.css')
        cls.settings_js_path = os.path.join(BASE_DIR, 'web', 'js', 'settings.js')

        with open(cls.html_path, 'r', encoding='utf-8') as f:
            cls.html_content = f.read()
        with open(cls.modals_css_path, 'r', encoding='utf-8') as f:
            cls.modals_css_content = f.read()
        with open(cls.styles_css_path, 'r', encoding='utf-8') as f:
            cls.styles_css_content = f.read()
        with open(cls.settings_js_path, 'r', encoding='utf-8') as f:
            cls.settings_js_content = f.read()

        # 2. Inicia instância isolada do Chrome Headless para testes E2E reais no navegador
        cls.cdp_port = find_free_port()
        user_data = f"/tmp/test-chrome-omni-{cls.cdp_port}"
        cls.chrome_proc = subprocess.Popen([
            '/usr/bin/google-chrome',
            '--headless=new',
            f'--remote-debugging-port={cls.cdp_port}',
            f'--user-data-dir={user_data}',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-extensions',
            'http://127.0.0.1:8765'
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Aguarda porta do Chrome e captura a URL WebSocket da página
        for _ in range(40):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{cls.cdp_port}/json/list', timeout=1.0) as r:
                    targets = json.loads(r.read().decode())
                    pages = [t for t in targets if t.get('type') == 'page' and '8765' in t.get('url', '')]
                    if pages:
                        cls.ws_url = pages[0]['webSocketDebuggerUrl']
                        break
            except Exception:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        if cls.chrome_proc:
            try:
                cls.chrome_proc.terminate()
                cls.chrome_proc.wait(timeout=2.0)
            except Exception:
                pass

    async def _evaluate_cdp(self, expression, await_promise=False):
        """Helper assíncrono para avaliar expressões JavaScript na página aberta via CDP."""
        self.assertIsNotNone(self.ws_url, "Chrome DevTools WebSocket não está disponível.")
        async with websockets.connect(self.ws_url) as ws:
            req_id = int(time.time() * 1000) % 100000
            msg = {
                "id": req_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": expression,
                    "returnByValue": True,
                    "awaitPromise": await_promise
                }
            }
            await ws.send(json.dumps(msg))
            while True:
                raw = await ws.recv()
                data = json.loads(raw)
                if data.get("id") == req_id:
                    if "exceptionDetails" in data.get("result", {}):
                        raise RuntimeError(f"CDP JS Exception: {data['result']['exceptionDetails']}")
                    return data.get("result", {}).get("result", {}).get("value")

    def run_cdp(self, expression, await_promise=False):
        """Wrapper síncrono para executar comandos JS no Chrome."""
        return asyncio.run(self._evaluate_cdp(expression, await_promise))

    def wait_for_cockpit_ready(self):
        """Garante que o DOM esteja pronto e todos os módulos ES inicializados."""
        for _ in range(50):
            st = self.run_cdp("""
                (function() {
                    return document.readyState === 'complete' && typeof window.openOmniRouteAccountModal === 'function';
                })()
            """)
            if st is True:
                return True
            time.sleep(0.1)
        return False

    # =========================================================================
    # 1. TESTES ESTRUTURAIS DE HTML
    # =========================================================================
    def test_html_modal_and_button_structure(self):
        """Valida que o HTML contém os elementos necessários para conectar conta OmniRoute."""
        html = self.html_content

        # Botão Conectar Conta no header da seção de contas
        self.assertIn('id="btn-add-omniroute-account"', html)
        self.assertIn('Conectar Conta', html)

        # Modal de Conectar Conta
        self.assertIn('id="modal-omniroute-account"', html)

        # Elementos internos do formulário
        self.assertIn('id="ag-omni-provider-pills"', html)
        self.assertIn('id="omni-account-name"', html)
        self.assertIn('id="omni-account-key"', html)
        self.assertIn('id="omni-account-baseurl"', html)
        self.assertIn('id="omni-account-default-model"', html)
        self.assertIn('id="btn-save-omni-account"', html)
        self.assertIn('id="btn-cancel-omni-account"', html)
        self.assertIn('id="btn-close-omni-account-modal"', html)

    # =========================================================================
    # 2. TESTES DE CSS & Z-INDEX (HIERARQUIA VISUAL)
    # =========================================================================
    def test_css_modal_z_index_hierarchy(self):
        """
        O modal de configurações (#modal-settings-antigravity) possui z-index: 1000.
        O modal #modal-omniroute-account é aberto a partir dele e DEVE possuir z-index estritamente maior
        (ex: z-index >= 2000) no CSS compilado para nunca abrir atrás da tela de configurações.
        """
        modals_css = self.modals_css_content
        self.assertTrue(
            '#modal-omniroute-account' in modals_css or '.omni-account-backdrop' in modals_css,
            "modals.css DEVE definir uma regra de estilo específica para #modal-omniroute-account ou .omni-account-backdrop"
        )

        # Verifica menção explícita de z-index alto para #modal-omniroute-account
        self.assertTrue(
            ('modal-omniroute-account' in modals_css and 'z-index: 2' in modals_css) or
            ('modal-omniroute-account' in modals_css and 'z-index: 1100' in modals_css) or
            ('modal-omniroute-account' in modals_css and 'z-index: 2000' in modals_css) or
            ('modal-omniroute-account' in modals_css and 'z-index: 2100' in modals_css),
            "#modal-omniroute-account DEVE ter z-index explicitamente definido maior que 1000 (ex: 2000 ou 2100) em modals.css"
        )

    # =========================================================================
    # 3. TESTES DE LÓGICA E EVENT LISTENERS EM SETTINGS.JS
    # =========================================================================
    def test_settings_js_modal_wiring(self):
        """Valida que settings.js possui os handlers, delegação e controle de estado do modal."""
        js = self.settings_js_content

        self.assertIn('openOmniRouteAccountModal', js)
        self.assertIn('closeOmniRouteAccountModal', js)
        self.assertIn('saveOmniRouteAccount', js)
        self.assertIn('selectOmniRouteProviderPill', js)

        # Listener do botão btn-add-omniroute-account
        self.assertIn('btn-add-omniroute-account', js)
        self.assertIn('openOmniRouteAccountModal', js)

    # =========================================================================
    # 4. TESTE REAL PONTA A PONTA NO GOOGLE CHROME HEADLESS
    # =========================================================================
    def test_browser_click_conectar_conta_opens_modal_above_settings(self):
        """
        Teste Real E2E no Navegador:
        1. Carrega página e aguarda bootstrap.
        2. Clica no botão do footer de configurações (#nav-footer-settings).
        3. Navega para a aba 'models' clicando em .ag-nav-item[data-ag-tab="models"].
        4. Clica no botão '#btn-add-omniroute-account'.
        5. Valida que #modal-omniroute-account está com display: 'flex'.
        6. Valida que o z-index computado de #modal-omniroute-account é ESTRITAMENTE MAIOR que o de #modal-settings-antigravity.
        7. Interage com as pílulas de provedor (ex: ollama ativa campo baseUrl).
        8. Clica em fechar e valida que o modal fecha, mantendo configurações abertas.
        """
        # Aguarda DOM pronto e módulos ES inicializados
        self.assertTrue(self.wait_for_cockpit_ready(), "A aplicação não completou o bootstrap em tempo hábil.")

        # Passo 1: Abre modal de configurações clicando no botão do footer
        opened_settings = self.run_cdp("""
            (function() {
                const btn = document.getElementById('nav-footer-settings');
                if (!btn) return false;
                btn.click();
                const s = document.getElementById('modal-settings-antigravity');
                return s && window.getComputedStyle(s).display !== 'none';
            })()
        """)
        self.assertTrue(opened_settings, "O modal de configurações (#modal-settings-antigravity) deve estar visível.")

        # Passo 2: Navega para aba models
        opened_tab = self.run_cdp("""
            (function() {
                const tab = document.querySelector('.ag-nav-item[data-ag-tab="models"]');
                if (!tab) return false;
                tab.click();
                const panel = document.getElementById('ag-panel-models');
                return panel && panel.classList.contains('active');
            })()
        """)
        self.assertTrue(opened_tab, "A aba 'models' (#ag-panel-models) deve estar ativa.")

        # Passo 3: Clica no botão "Conectar Conta"
        btn_clicked = self.run_cdp("""
            (function() {
                const btn = document.getElementById('btn-add-omniroute-account');
                if (!btn) return false;
                btn.click();
                return true;
            })()
        """)
        self.assertTrue(btn_clicked, "Botão #btn-add-omniroute-account não foi encontrado para clique.")

        # Passo 4: Valida que #modal-omniroute-account está com display: 'flex'
        modal_state = self.run_cdp("""
            (function() {
                const m = document.getElementById('modal-omniroute-account');
                if (!m) return { found: false };
                const style = window.getComputedStyle(m);
                return {
                    found: true,
                    display: style.display,
                    zIndex: parseInt(style.zIndex, 10) || 0
                };
            })()
        """)
        self.assertTrue(modal_state.get('found'), "Elemento #modal-omniroute-account deve existir no DOM.")
        self.assertEqual(modal_state.get('display'), 'flex', "O modal #modal-omniroute-account deve ter display: 'flex' após clique.")

        # Passo 5: Valida que o z-index computado do modal de conta é ESTRITAMENTE MAIOR que o de configurações
        settings_zindex = self.run_cdp("""
            (function() {
                const s = document.getElementById('modal-settings-antigravity');
                return parseInt(window.getComputedStyle(s).zIndex, 10) || 0;
            })()
        """)
        omni_modal_zindex = modal_state.get('zIndex')

        self.assertGreater(
            omni_modal_zindex,
            settings_zindex,
            f"O z-index do #modal-omniroute-account ({omni_modal_zindex}) DEVE ser estritamente maior que o do #modal-settings-antigravity ({settings_zindex}) para garantir sobreposição no navegador!"
        )

        # Passo 6: Testa alternância de provedor (Pílulas)
        # Seleciona Ollama e valida que o campo Base URL fica visível
        self.run_cdp("""
            (function() {
                const ollamaPill = document.querySelector('.ag-omni-provider-pill[data-provider="ollama"]');
                if (ollamaPill) ollamaPill.click();
            })()
        """)

        baseurl_visible = self.run_cdp("""
            (function() {
                const group = document.getElementById('omni-account-baseurl-group');
                return group && window.getComputedStyle(group).display !== 'none';
            })()
        """)
        self.assertTrue(baseurl_visible, "Ao selecionar Ollama, o campo Base URL deve ficar visível.")

        # Passo 7: Testa fechamento do modal da conta
        self.run_cdp("""
            (function() {
                const closeBtn = document.getElementById('btn-close-omni-account-modal');
                if (closeBtn) closeBtn.click();
            })()
        """)

        modal_closed = self.run_cdp("""
            (function() {
                const m = document.getElementById('modal-omniroute-account');
                return m && window.getComputedStyle(m).display === 'none';
            })()
        """)
        self.assertTrue(modal_closed, "O modal #modal-omniroute-account deve ter display: 'none' após clicar em fechar.")

        # Modal de configurações deve continuar aberto
        settings_still_open = self.run_cdp("""
            (function() {
                const s = document.getElementById('modal-settings-antigravity');
                return s && window.getComputedStyle(s).display !== 'none';
            })()
        """)
        self.assertTrue(settings_still_open, "O modal de configurações deve continuar aberto após fechar o modal de conta.")

    def test_browser_account_modal_validation_and_submission(self):
        """Valida que o formulário exibe feedback de validação em campos vazios."""
        self.assertTrue(self.wait_for_cockpit_ready(), "A aplicação não completou o bootstrap em tempo hábil.")

        # Abre o modal de configurações se fechado
        self.run_cdp("""
            (function() {
                const s = document.getElementById('modal-settings-antigravity');
                if (!s || window.getComputedStyle(s).display === 'none') {
                    const btn = document.getElementById('nav-footer-settings');
                    if (btn) btn.click();
                }
                const tab = document.querySelector('.ag-nav-item[data-ag-tab="models"]');
                if (tab) tab.click();
            })()
        """)

        # 1. Abre modal de conta
        self.run_cdp("""
            (function() {
                const btn = document.getElementById('btn-add-omniroute-account');
                if (btn) btn.click();
            })()
        """)

        # 2. Limpa o nome da conta e clica em salvar
        self.run_cdp("""
            (function() {
                const nameInput = document.getElementById('omni-account-name');
                if (nameInput) nameInput.value = '';
                const saveBtn = document.getElementById('btn-save-omni-account');
                if (saveBtn) saveBtn.click();
            })()
        """)

        # 3. Valida feedback de erro para nome obrigatório
        name_err = self.run_cdp("""
            (function() {
                const fb = document.getElementById('modal-omni-account-feedback');
                return fb && window.getComputedStyle(fb).display !== 'none' && fb.textContent.includes('informe um nome');
            })()
        """)
        self.assertTrue(name_err, "Deve exibir mensagem de erro se nome da conta não for preenchido.")

        # 4. Preenche nome, mas deixa chave de API vazia
        self.run_cdp("""
            (function() {
                const nameInput = document.getElementById('omni-account-name');
                if (nameInput) nameInput.value = 'Minha Conta OpenAI';
                const keyInput = document.getElementById('omni-account-key');
                if (keyInput) keyInput.value = '';
                const saveBtn = document.getElementById('btn-save-omni-account');
                if (saveBtn) saveBtn.click();
            })()
        """)

        key_err = self.run_cdp("""
            (function() {
                const fb = document.getElementById('modal-omni-account-feedback');
                return fb && window.getComputedStyle(fb).display !== 'none' && fb.textContent.includes('chave de API');
            })()
        """)
        self.assertTrue(key_err, "Deve exibir erro quando chave de API não for preenchida.")

        # 5. Seleciona Ollama, limpa endpoint Base URL
        self.run_cdp("""
            (function() {
                const ollamaPill = document.querySelector('.ag-omni-provider-pill[data-provider="ollama"]');
                if (ollamaPill) ollamaPill.click();
                const baseUrlInput = document.getElementById('omni-account-baseurl');
                if (baseUrlInput) baseUrlInput.value = '';
                const saveBtn = document.getElementById('btn-save-omni-account');
                if (saveBtn) saveBtn.click();
            })()
        """)

        baseurl_err = self.run_cdp("""
            (function() {
                const fb = document.getElementById('modal-omni-account-feedback');
                return fb && window.getComputedStyle(fb).display !== 'none' && fb.textContent.includes('Base URL');
            })()
        """)
        self.assertTrue(baseurl_err, "Deve exibir erro quando Base URL não for informada para Ollama.")

        # 6. Fecha modal
        self.run_cdp("""
            (function() {
                const cancelBtn = document.getElementById('btn-cancel-omni-account');
                if (cancelBtn) cancelBtn.click();
            })()
        """)

    # =========================================================================
    # 5. TESTES E2E DE CONEXÃO DIRETA / OAUTH (SEM CHAVE DE API)
    # =========================================================================
    def test_browser_direct_accounts_tab_and_cards_rendered(self):
        """Valida que a aba de Conexão Direta (Sem Chave) abre por padrão e renderiza os cards de provedores."""
        self.assertTrue(self.wait_for_cockpit_ready(), "A aplicação não completou o bootstrap em tempo hábil.")

        # Abre modal de conta
        self.run_cdp("""
            (function() {
                const btn = document.getElementById('btn-add-omniroute-account');
                if (btn) btn.click();
            })()
        """)

        # 1. Valida que a aba Direct está ativa por padrão
        is_direct_active = self.run_cdp("""
            (function() {
                const tab = document.getElementById('tab-omni-direct');
                const panel = document.getElementById('omni-panel-direct');
                return tab && tab.classList.contains('active') && panel && window.getComputedStyle(panel).display !== 'none';
            })()
        """)
        self.assertTrue(is_direct_active, "A aba 'Conexão Direta (Sem Chave)' deve estar selecionada e ativa por padrão.")

        # 2. Valida que os cards de provedores diretos foram renderizados
        rendered_providers = self.run_cdp("""
            (function() {
                const cards = document.querySelectorAll('.omni-direct-card');
                return Array.from(cards).map(c => c.dataset.directProvider);
            })()
        """)
        self.assertIn("antigravity", rendered_providers)
        self.assertIn("claude-code", rendered_providers)
        self.assertIn("copilot", rendered_providers)
        self.assertIn("cursor", rendered_providers)
        self.assertIn("codex", rendered_providers)

        # Fecha modal
        self.run_cdp("""
            (function() {
                const cancelBtn = document.getElementById('btn-cancel-omni-account');
                if (cancelBtn) cancelBtn.click();
            })()
        """)

    def test_browser_switch_tabs_between_direct_and_apikey(self):
        """Valida alternância suave entre abas 'Conexão Direta' e 'Chave Manual'."""
        self.assertTrue(self.wait_for_cockpit_ready(), "A aplicação não completou o bootstrap em tempo hábil.")

        # Abre modal de conta
        self.run_cdp("""
            (function() {
                const btn = document.getElementById('btn-add-omniroute-account');
                if (btn) btn.click();
            })()
        """)

        # Clica na aba Chave Manual
        self.run_cdp("""
            (function() {
                const tabApiKey = document.getElementById('tab-omni-apikey');
                if (tabApiKey) tabApiKey.click();
            })()
        """)

        apikey_active = self.run_cdp("""
            (function() {
                const panelApiKey = document.getElementById('omni-panel-apikey');
                const panelDirect = document.getElementById('omni-panel-direct');
                const btnSave = document.getElementById('btn-save-omni-account');
                return (
                    panelApiKey && window.getComputedStyle(panelApiKey).display !== 'none' &&
                    panelDirect && window.getComputedStyle(panelDirect).display === 'none' &&
                    btnSave && window.getComputedStyle(btnSave).display !== 'none'
                );
            })()
        """)
        self.assertTrue(apikey_active, "Aba Chave Manual deve exibir seu formulário e o botão Conectar com Chave.")

        # Volta para aba Conexão Direta
        self.run_cdp("""
            (function() {
                const tabDirect = document.getElementById('tab-omni-direct');
                if (tabDirect) tabDirect.click();
            })()
        """)

        direct_active = self.run_cdp("""
            (function() {
                const panelDirect = document.getElementById('omni-panel-direct');
                const panelApiKey = document.getElementById('omni-panel-apikey');
                return (
                    panelDirect && window.getComputedStyle(panelDirect).display !== 'none' &&
                    panelApiKey && window.getComputedStyle(panelApiKey).display === 'none'
                );
            })()
        """)
        self.assertTrue(direct_active, "Aba Conexão Direta deve voltar a ficar visível.")

        # Fecha modal
        self.run_cdp("""
            (function() {
                const cancelBtn = document.getElementById('btn-cancel-omni-account');
                if (cancelBtn) cancelBtn.click();
            })()
        """)

    def test_browser_click_cursor_import_card(self):
        """Valida clique no card do Cursor IDE renderizando a caixa de ação de importação local."""
        self.assertTrue(self.wait_for_cockpit_ready(), "A aplicação não completou o bootstrap em tempo hábil.")

        self.run_cdp("""
            (function() {
                const btn = document.getElementById('btn-add-omniroute-account');
                if (btn) btn.click();
            })()
        """)

        # Clica no card do Cursor
        self.run_cdp("""
            (function() {
                const cursorCard = document.querySelector('.omni-direct-card[data-direct-provider="cursor"]');
                if (cursorCard) cursorCard.click();
            })()
        """)

        action_rendered = self.run_cdp("""
            (function() {
                const box = document.getElementById('omni-direct-action-box');
                const btnRun = document.getElementById('btn-run-local-import');
                return box && window.getComputedStyle(box).display !== 'none' && btnRun !== null;
            })()
        """)
        self.assertTrue(action_rendered, "Ao selecionar Cursor, a caixa de ação deve exibir o botão de importação local.")

        # Fecha modal
        self.run_cdp("""
            (function() {
                const cancelBtn = document.getElementById('btn-cancel-omni-account');
                if (cancelBtn) cancelBtn.click();
            })()
        """)

    def test_browser_click_antigravity_oauth_card_and_paste_url(self):
        """Valida que ao clicar em Google Antigravity, a dica da porta 8080 é exibida e o input detecta URLs de callback."""
        self.assertTrue(self.wait_for_cockpit_ready(), "A aplicação não completou o bootstrap em tempo hábil.")

        self.run_cdp("""
            (function() {
                const btn = document.getElementById('btn-add-omniroute-account');
                if (btn) btn.click();
            })()
        """)

        # Clica no card do Google Antigravity
        self.run_cdp("""
            (function() {
                const card = document.querySelector('.omni-direct-card[data-direct-provider="antigravity"]');
                if (card) card.click();
            })()
        """)

        # Aguarda a caixa de ação renderizar (polling até 5s)
        for _ in range(25):
            ready = self.run_cdp("""
                (function() {
                    return document.getElementById('omni-oauth-code-input') !== null;
                })()
            """)
            if ready:
                break
            time.sleep(0.2)

        action_data = self.run_cdp("""
            (function() {
                const box = document.getElementById('omni-direct-action-box');
                const loopbackHint = document.querySelector('.oauth-loopback-hint');
                const btnPaste = document.getElementById('btn-omni-paste-oauth');
                const inputCode = document.getElementById('omni-oauth-code-input');
                const feedback = document.getElementById('omni-oauth-code-feedback');

                // Simula colar a URL de callback retornada pelo Google
                if (inputCode) {
                    inputCode.value = 'http://localhost:8080/callback?state=ZKmszU87nlnisU&code=4/0AW_google_code_123';
                    inputCode.dispatchEvent(new Event('input'));
                }

                return {
                    boxVisible: box && window.getComputedStyle(box).display !== 'none',
                    hasHint: loopbackHint !== null && loopbackHint.textContent.includes('8080'),
                    hasPasteBtn: btnPaste !== null,
                    feedbackVisible: feedback && window.getComputedStyle(feedback).display !== 'none',
                    feedbackText: feedback ? feedback.textContent : ''
                };
            })()
        """)

        self.assertIsNotNone(action_data)
        self.assertTrue(action_data.get("boxVisible"), "Caixa de ação direta deve estar visível.")
        self.assertTrue(action_data.get("hasHint"), "Dica explicativa sobre a porta 8080 e redirecionamento deve estar presente.")
        self.assertTrue(action_data.get("hasPasteBtn"), "Botão de colar da área de transferência deve estar presente.")
        self.assertTrue(action_data.get("feedbackVisible"), "Feedback de detecção de URL deve ser exibido.")
        self.assertIn("URL", action_data.get("feedbackText", ""))

        # Fecha modal
        self.run_cdp("""
            (function() {
                const cancelBtn = document.getElementById('btn-cancel-omni-account');
                if (cancelBtn) cancelBtn.click();
            })()
        """)

    def test_browser_omniroute_hub_button(self):
        """Valida que o botão de atalho Central OmniRoute está visível com URL correta."""
        hub_info = self.run_cdp("""
            (function() {
                const btn = document.getElementById('btn-open-omniroute-hub');
                if (!btn) return null;
                return {
                    href: btn.getAttribute('href'),
                    target: btn.getAttribute('target'),
                    text: btn.textContent.trim()
                };
            })()
        """)
        self.assertIsNotNone(hub_info, "Botão #btn-open-omniroute-hub deve estar presente no DOM.")
        self.assertEqual(hub_info.get('target'), '_blank', "Deve abrir em nova aba (_blank).")
        self.assertIn('20128', hub_info.get('href'), "Deve apontar para o servidor do OmniRoute (porta 20128).")


if __name__ == '__main__':
    unittest.main()
