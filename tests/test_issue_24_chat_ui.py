import unittest
import os
import subprocess
import json

class TestIssue24ChatUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.zeus_chat_js_path = os.path.join(cls.base_dir, 'web', 'js', 'zeus_chat_ui.js')
        cls.css_path = os.path.join(cls.base_dir, 'web', 'styles.css')
        cls.html_path = os.path.join(cls.base_dir, 'web', 'index.html')
        cls.app_js_path = os.path.join(cls.base_dir, 'web', 'app.js')

        if os.path.exists(cls.zeus_chat_js_path):
            with open(cls.zeus_chat_js_path, 'r', encoding='utf-8') as f:
                cls.zeus_chat_js_content = f.read()
        else:
            cls.zeus_chat_js_content = ""

        with open(cls.css_path, 'r', encoding='utf-8') as f:
            cls.css_content = f.read()

        with open(cls.html_path, 'r', encoding='utf-8') as f:
            cls.html_content = f.read()

        with open(cls.app_js_path, 'r', encoding='utf-8') as f:
            cls.app_js_content = f.read()

    def test_01_zeus_chat_js_file_exists_and_exports_api(self):
        """Valida que web/js/zeus_chat_ui.js existe e exporta a API requerida."""
        self.assertTrue(os.path.exists(self.zeus_chat_js_path), "web/js/zeus_chat_ui.js deve existir")
        js = self.zeus_chat_js_content

        self.assertIn('class ZeusChatUI', js, "Deve definir a classe ZeusChatUI")
        self.assertIn('export const zeusChatUI', js, "Deve exportar a instância zeusChatUI")
        self.assertIn('export function initZeusChatUI', js, "Deve exportar a função initZeusChatUI")
        self.assertIn('window.zeusChatUI', js, "Deve expor zeusChatUI em window")
        self.assertIn('window.initZeusChatUI', js, "Deve expor initZeusChatUI em window")

    def test_02_thinking_box_rendering_and_auto_expansion(self):
        """Valida blocos de raciocínio expansíveis (<details class='zeus-thinking-box'>) com auto-expansão no streaming."""
        js = self.zeus_chat_js_content

        self.assertIn('zeus-thinking-box', js, "Deve utilizar a classe zeus-thinking-box para details de pensamento")
        self.assertIn('details', js.lower(), "Deve instanciar ou renderizar tag <details>")
        self.assertIn('summary', js.lower(), "Deve conter elemento <summary> para colapsar/expandir o raciocínio")
        
        # Auto-expansão durante o streaming
        self.assertTrue(
            'open' in js and ('streaming' in js.lower() or 'isstreaming' in js.lower() or 'autoexpand' in js.lower() or 'details.open' in js or 'thinkbox.open' in js),
            "Deve conter lógica de auto-expansão (open = true) durante o streaming de pensamento"
        )

    def test_03_tool_calls_cards_rendering(self):
        """Valida cards de Tool Calls especializados (arquivos lidos/escritos, comandos executados)."""
        js = self.zeus_chat_js_content

        self.assertIn('zeus-tool-card', js, "Deve utilizar a classe zeus-tool-card para os cards de ferramentas")
        
        # Suporte a operações com arquivos e comandos
        self.assertTrue(
            ('read_file' in js or 'read' in js.lower()) and 
            ('write_file' in js or 'write' in js.lower()),
            "Deve haver tratamento e identificação de ferramentas de leitura e escrita de arquivos"
        )
        self.assertTrue(
            'bash' in js.lower() or 'command' in js.lower() or 'exec' in js.lower(),
            "Deve haver tratamento para execução de comandos de terminal/bash"
        )

        # Badges/status de ferramentas
        self.assertTrue(
            'tool-badge' in js or 'tool-status' in js or 'tool-name' in js,
            "Deve renderizar badges ou status de execução da ferramenta"
        )

    def test_04_contextual_model_selector(self):
        """Valida seletor de modelos contextual alimentado por /api/omniroute/connectors e /api/local-worker/models."""
        js = self.zeus_chat_js_content

        self.assertIn('/api/omniroute/connectors', js, "Deve consumir o endpoint /api/omniroute/connectors")
        self.assertIn('/api/local-worker/models', js, "Deve consumir o endpoint /api/local-worker/models")
        self.assertIn('zeus-model-select', js, "Deve referenciar ou criar elemento zeus-model-select")
        
        # Detecção de visão / multimodalidade do modelo
        self.assertTrue(
            'isVisionSupported' in js or 'supportsVision' in js or 'vision' in js.lower(),
            "Deve implementar método para checar se modelo suporta visão"
        )

    def test_05_skills_and_mcps_popover_dropdown(self):
        """Valida dropdown suspenso / popover com checkboxes para selecionar Skills e MCPs."""
        js = self.zeus_chat_js_content

        self.assertIn('zeus-skills-popover', js, "Deve referenciar/criar menu popover zeus-skills-popover")
        self.assertIn('/api/customizations/mcp', js, "Deve consumir /api/customizations/mcp")
        self.assertIn('/api/customizations/skills', js, "Deve consumir /api/customizations/skills")
        
        # Checkboxes para alternar ativação dinâmica
        self.assertIn('checkbox', js.lower(), "Deve conter elementos checkbox para ativação dinâmica")
        
        # Método para obter seleções ativas
        self.assertTrue(
            'getSelectedCustomizations' in js or 'selectedSkills' in js or 'selectedMcps' in js,
            "Deve gerenciar lista de Skills e Servidores MCP selecionados dinamicamente"
        )

    def test_06_microphone_stt_button(self):
        """Valida botão de microfone com captura MediaRecorder, animação e endpoint de transcrição."""
        js = self.zeus_chat_js_content

        self.assertIn('zeus-btn-mic', js, "Deve conter botão de microfone zeus-btn-mic")
        self.assertIn('MediaRecorder', js, "Deve utilizar a API nativa MediaRecorder para captura de áudio")
        self.assertIn('/api/audio/transcribe-and-optimize', js, "Deve enviar áudio para /api/audio/transcribe-and-optimize")
        
        # Animação/classe de gravação
        self.assertTrue(
            'recording' in js.lower(),
            "Deve alternar classe ou estado 'recording' para animação visual de gravação"
        )

    def test_07_multimodal_image_attachment_and_validation(self):
        """Valida anexo de imagens (botão, drag-drop, paste), thumbnails e validação de visão sem perda de texto."""
        js = self.zeus_chat_js_content

        # 3 formas de anexo
        self.assertIn('dragover', js.lower(), "Deve suportar drag-and-drop (evento dragover)")
        self.assertIn('drop', js.lower(), "Deve suportar drag-and-drop (evento drop)")
        self.assertIn('paste', js.lower(), "Deve suportar colar da área de transferência (evento paste / Ctrl+V)")
        self.assertTrue(
            'btn-zeus-attach-img' in js or 'zeus-btn-attach' in js or 'attach' in js.lower(),
            "Deve conter botão para anexo de imagens"
        )

        # Thumbnails de preview com botão de remover
        self.assertIn('zeus-attachments-preview', js, "Deve conter container de preview de anexos")
        self.assertTrue(
            'remove' in js.lower() and ('thumb' in js.lower() or 'attachment' in js.lower()),
            "Deve permitir remover thumbnails individualmente"
        )

        # Validação de visão: se modelo não aceitar visão, exibe erro em badge vermelho sem perder texto
        self.assertTrue(
            'badge-danger' in js or 'zeus-vision-error' in js or 'zeus-model-warning' in js or 'badge' in js.lower(),
            "Deve exibir badge vermelho de erro se modelo não suportar visão"
        )

    def test_08_styles_css_zeus_chat_definitions(self):
        """Valida que web/styles.css define os estilos do tema dark e ciano para a UI Zeus."""
        css = self.css_content

        required_classes = [
            '.zeus-thinking-box',
            '.zeus-tool-card',
            '.zeus-model-select',
            '.zeus-skills-popover',
            '.zeus-btn-mic',
            '.zeus-attachments-preview',
            '.zeus-attachment-thumb'
        ]
        for rc in required_classes:
            self.assertIn(rc, css, f"styles.css deve conter definição de estilo para {rc}")

        # Animação de pulso para gravação de microfone
        self.assertTrue(
            '@keyframes' in css and ('pulse' in css.lower() or 'record' in css.lower() or 'mic' in css.lower()),
            "styles.css deve conter animação keyframes para efeito pulsante do microfone em gravação"
        )

        # Estilização em ciano do tema do Cockpit
        self.assertTrue(
            'cyan' in css.lower() or '#00e5ff' in css.lower() or '#00f0ff' in css.lower() or '0, 229, 255' in css or '--accent-cyan' in css,
            "styles.css deve utilizar acentos ciano do Cockpit na caixa de raciocínio e elementos Zeus"
        )

    def test_09_html_and_app_js_integration(self):
        """Valida que web/index.html e web/app.js integram e inicializam a Zeus Chat UI."""
        html = self.html_content
        app_js = self.app_js_content

        # index.html deve conter elementos ou container do Zeus Chat
        self.assertTrue(
            'zeus-chat-container' in html or 'opencode-visual-chat-container' in html,
            "web/index.html deve conter o container de chat visual do Cockpit"
        )

        # app.js deve importar e inicializar zeus_chat_ui
        self.assertIn('zeus_chat_ui.js', app_js, "web/app.js deve importar o módulo zeus_chat_ui.js")
        self.assertIn('initZeusChatUI', app_js, "web/app.js deve chamar initZeusChatUI no ciclo de vida")

    def test_10_node_functional_unit_behavior(self):
        """Valida o comportamento funcional das funções centrais do zeus_chat_ui.js executando em Node.js."""
        node_script = f"""
        const fs = require('fs');
        const vm = require('vm');

        // Cria ambiente DOM simulado
        const mockElements = new Map();
        function createMockElement(tag, id = '') {{
            const el = {{
                tagName: tag.toUpperCase(),
                id: id,
                className: '',
                classList: {{
                    add: (c) => {{ if (!el.className.includes(c)) el.className += ' ' + c; }},
                    remove: (c) => {{ el.className = el.className.replace(c, '').trim(); }},
                    contains: (c) => el.className.includes(c),
                    toggle: (c, force) => {{
                        if (force !== undefined) {{
                            if (force) el.classList.add(c); else el.classList.remove(c);
                        }} else {{
                            if (el.classList.contains(c)) el.classList.remove(c); else el.classList.add(c);
                        }}
                    }}
                }},
                style: {{ display: 'block' }},
                children: [],
                childNodes: [],
                innerHTML: '',
                textContent: '',
                value: '',
                open: false,
                attributes: {{}},
                setAttribute: (k, v) => {{ el.attributes[k] = v; if (k === 'open') el.open = true; }},
                getAttribute: (k) => el.attributes[k] || null,
                removeAttribute: (k) => {{ delete el.attributes[k]; if (k === 'open') el.open = false; }},
                appendChild: (child) => {{ el.children.push(child); el.childNodes.push(child); return child; }},
                addEventListener: (evt, handler) => {{}},
                removeEventListener: (evt, handler) => {{}},
                querySelector: () => null,
                querySelectorAll: () => [],
                focus: () => {{}},
                remove: () => {{}}
            }};
            return el;
        }}

        const mockDoc = {{
            createElement: (tag) => createMockElement(tag),
            getElementById: (id) => {{
                if (!mockElements.has(id)) {{
                    mockElements.set(id, createMockElement('div', id));
                }}
                return mockElements.get(id);
            }},
            querySelectorAll: () => [],
            querySelector: () => null,
            body: createMockElement('body')
        }};

        global.window = {{
            document: mockDoc,
            location: {{ protocol: 'http:', host: 'localhost:8765' }}
        }};
        global.document = mockDoc;
        global.navigator = {{
            mediaDevices: {{
                getUserMedia: async () => ({{ getTracks: () => [{{ stop: () => {{}} }}] }})
            }}
        }};

        // Carrega código de zeus_chat_ui.js removendo import/export ES modules para VM
        let code = fs.readFileSync('{self.zeus_chat_js_path}', 'utf-8');
        code = code.replace(/import\\s+.*?from\\s+['"].*?['"];?/g, '');
        code = code.replace(/export\\s+const\\s+/g, 'const ');
        code = code.replace(/export\\s+function\\s+/g, 'function ');
        code = code.replace(/export\\s+class\\s+/g, 'class ');
        code = code.replace(/export\\s+default\\s+/g, '');

        const context = vm.createContext({{
            window: global.window,
            document: mockDoc,
            navigator: global.navigator,
            console,
            setTimeout,
            clearTimeout,
            setInterval,
            clearInterval,
            fetch: async () => ({{ ok: true, json: async () => ({{ status: 'ok' }}) }}),
            MediaRecorder: class {{
                constructor() {{ this.state = 'inactive'; }}
                start() {{ this.state = 'recording'; }}
                stop() {{ this.state = 'inactive'; if (this.onstop) this.onstop(); }}
                addEventListener() {{}}
            }}
        }});

        vm.runInContext(code, context);

        const ZeusChatUI = context.ZeusChatUI || context.window.ZeusChatUI;
        if (!ZeusChatUI) {{
            throw new Error('ZeusChatUI não encontrado no escopo');
        }}

        const instance = new ZeusChatUI();

        // 1. Testa detecção de suporte a visão
        const hasVisionGPT4o = instance.isVisionSupported('gpt-4o');
        const hasVisionClaude = instance.isVisionSupported('claude-3-5-sonnet');
        const hasVisionLlava = instance.isVisionSupported('llava:latest');
        const noVisionQwen = instance.isVisionSupported('qwen2.5-coder:7b');
        const noVisionGPT35 = instance.isVisionSupported('gpt-3.5-turbo');

        if (!hasVisionGPT4o || !hasVisionClaude || !hasVisionLlava) {{
            throw new Error('isVisionSupported falhou ao identificar modelos com visão');
        }}
        if (noVisionQwen || noVisionGPT35) {{
            throw new Error('isVisionSupported identificou falsamente visão em modelo puramente texto/código');
        }}

        // 2. Testa criação de bloco de pensamento com auto-expansão
        const thinkBoxOpen = instance.createThinkingBox('Calculando melhor estratégia...', true);
        if (!thinkBoxOpen.open) {{
            throw new Error('Thinking box não está aberta (open=true) durante streaming');
        }}
        if (!thinkBoxOpen.className.includes('zeus-thinking-box')) {{
            throw new Error('Thinking box não possui classe zeus-thinking-box');
        }}

        // 3. Testa criação de card de Tool Call
        const fileToolCard = instance.createToolCard({{
            name: 'write_file',
            detail: '/src/main.rs',
            status: 'success'
        }});
        if (!fileToolCard.className.includes('zeus-tool-card')) {{
            throw new Error('Tool card não possui classe zeus-tool-card');
        }}

        const cmdToolCard = instance.createToolCard({{
            name: 'bash',
            detail: 'cargo check',
            status: 'running'
        }});
        if (!cmdToolCard.innerHTML.includes('EXEC') && !cmdToolCard.innerHTML.includes('BASH') && !cmdToolCard.innerHTML.includes('bash')) {{
            throw new Error('Tool card de comando não exibe badge ou identificação adequada de execução');
        }}

        // 4. Testa validação multimodal: bloqueia envio se modelo não tiver visão, sem perder texto
        instance.selectedModel = 'qwen2.5-coder:7b';
        instance.attachedImages = [{{ name: 'screenshot.png', dataUrl: 'data:image/png;base64,123' }}];
        instance.chatInput = {{ value: 'Analise esta imagem com o código' }};
        const validation = instance.validateMultimodalInput();
        if (validation.valid !== false) {{
            throw new Error('Deveria invalidar envio com imagem para modelo sem visão');
        }}
        if (instance.chatInput.value !== 'Analise esta imagem com o código') {{
            throw new Error('Texto digitado não pode ser perdido após falha de validação');
        }}

        console.log(JSON.stringify({{ success: true }}));
        """

        res = subprocess.run(
            ['node', '-e', node_script],
            capture_output=True,
            text=True
        )
        self.assertEqual(res.returncode, 0, f"Falha na validação funcional via Node.js:\nStdout: {res.stdout}\nStderr: {res.stderr}")
        self.assertIn('"success":true', res.stdout)

if __name__ == '__main__':
    unittest.main()
