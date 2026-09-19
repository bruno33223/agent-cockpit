import os
import subprocess
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AVATAR_JS_PATH = os.path.join(BASE_DIR, "web", "js", "avatar_3d.js")
AVATAR_CSS_PATH = os.path.join(BASE_DIR, "web", "css", "avatar_3d.css")
TEST_FILE_PATH = os.path.abspath(__file__)

EXPECTED_STATES = [
    "IDLE",
    "LISTENING",
    "THINKING",
    "DISPATCHING_WORKER",
    "TESTING",
    "SPEAKING",
]


class TestAvatarStateEvents(unittest.TestCase):
    """Suíte de testes TDD para a Issue #45: Avatar Tático Holográfico 3D Procedural."""

    def test_01_files_exist(self):
        """Valida a existência dos arquivos web/js/avatar_3d.js e web/css/avatar_3d.css."""
        self.assertTrue(os.path.isfile(AVATAR_JS_PATH), "web/js/avatar_3d.js deve existir")
        self.assertTrue(os.path.isfile(AVATAR_CSS_PATH), "web/css/avatar_3d.css deve existir")

    def test_02_line_count_guardrails(self):
        """Guardrails estritos de contagem de linhas (JS <= 350, CSS <= 200, TEST <= 400)."""
        self.assertTrue(os.path.isfile(AVATAR_JS_PATH), "web/js/avatar_3d.js deve existir para verificar linhas")
        self.assertTrue(os.path.isfile(AVATAR_CSS_PATH), "web/css/avatar_3d.css deve existir para verificar linhas")

        with open(AVATAR_JS_PATH, "r", encoding="utf-8") as f:
            js_lines = len(f.readlines())
        with open(AVATAR_CSS_PATH, "r", encoding="utf-8") as f:
            css_lines = len(f.readlines())
        with open(TEST_FILE_PATH, "r", encoding="utf-8") as f:
            test_lines = len(f.readlines())

        self.assertLessEqual(js_lines, 350, f"avatar_3d.js tem {js_lines} linhas; limite estrito é <= 350")
        self.assertLessEqual(css_lines, 200, f"avatar_3d.css tem {css_lines} linhas; limite estrito é <= 200")
        self.assertLessEqual(test_lines, 400, f"test_avatar_state_events.py tem {test_lines} linhas; limite estrito é <= 400")

    def test_03_js_static_contract_and_no_heavy_downloads(self):
        """Valida que o JS define métodos públicos requeridos e não depende de downloads pesados (.glb/.vrm)."""
        with open(AVATAR_JS_PATH, "r", encoding="utf-8") as f:
            js_code = f.read()

        required_methods = ["init", "setState", "updateAudioLevel", "getState", "destroy"]
        for method in required_methods:
            self.assertIn(method, js_code, f"avatar_3d.js deve implementar o método público '{method}'")

        # Zero dependência de downloads de assets 3D pesados
        self.assertNotIn(".glb", js_code.lower(), "avatar_3d.js não deve depender de arquivos .glb")
        self.assertNotIn(".vrm", js_code.lower(), "avatar_3d.js não deve depender de arquivos .vrm")
        self.assertNotIn(".gltf", js_code.lower(), "avatar_3d.js não deve depender de arquivos .gltf")

        # Todos os 5 estados requeridos devem estar declarados
        for st in EXPECTED_STATES:
            self.assertIn(st, js_code, f"avatar_3d.js deve conter referência ao estado '{st}'")

    def test_04_css_glassmorphism_and_dock_support(self):
        """Valida que avatar_3d.css implementa glassmorphism e docas retráteis/flutuantes."""
        with open(AVATAR_CSS_PATH, "r", encoding="utf-8") as f:
            css_code = f.read()

        # Efeito glassmorphism escuro
        self.assertIn("backdrop-filter", css_code, "avatar_3d.css deve incluir backdrop-filter para glassmorphism")
        self.assertIn("rgba(", css_code, "avatar_3d.css deve usar fundos translúcidos (rgba)")

        # Classes de dock e viewport
        self.assertTrue(
            "avatar-3d-dock" in css_code or "tactical-avatar-dock" in css_code or "avatar-dock" in css_code,
            "avatar_3d.css deve conter classes para dock do avatar"
        )
        self.assertTrue(
            "floating" in css_code or "dock-floating" in css_code,
            "avatar_3d.css deve suportar dock flutuante (ex: Zeus Chat)"
        )
        self.assertTrue(
            "collapsed" in css_code or "dock-collapsed" in css_code or "is-collapsed" in css_code,
            "avatar_3d.css deve suportar dock retrátil/colapsável"
        )

        # Suporte aos estados no CSS
        for st in ["LISTENING", "THINKING", "DISPATCHING_WORKER", "TESTING", "SPEAKING"]:
            self.assertIn(st.lower(), css_code.lower(), f"avatar_3d.css deve conter regras visuais para {st}")

    def test_05_node_execution_api_lifecycle_and_fallback(self):
        """Executa avatar_3d.js via Node.js validando ciclo de vida, fallback Canvas 2D e Three.js procedural."""
        node_script = f"""
        const fs = require('fs');
        const vm = require('vm');

        function createMockDOM() {{
            const listeners = {{}};
            const element = {{
                tagName: 'DIV', id: 'avatar-container', className: '',
                classList: {{
                    add: (c) => {{ if (!element.className.includes(c)) element.className = (element.className + ' ' + c).trim(); }},
                    remove: (c) => {{ element.className = element.className.replace(c, '').trim(); }},
                    contains: (c) => element.className.includes(c)
                }},
                attributes: {{}}, dataset: {{}}, style: {{}}, children: [], childNodes: [], innerHTML: '',
                appendChild: (ch) => {{ element.children.push(ch); element.childNodes.push(ch); ch.parentNode = element; return ch; }},
                removeChild: (ch) => {{
                    const idx = element.children.indexOf(ch);
                    if (idx >= 0) element.children.splice(idx, 1);
                    return ch;
                }},
                setAttribute: (k, v) => {{
                    element.attributes[k] = v;
                    if (k.startsWith('data-')) {{
                        const dKey = k.slice(5).replace(/-([a-z])/g, (_, g) => g.toUpperCase());
                        element.dataset[dKey] = v;
                    }}
                }},
                getAttribute: (k) => element.attributes[k] || null,
                removeAttribute: (k) => {{ delete element.attributes[k]; }},
                addEventListener: (evt, fn) => {{ listeners[evt] = listeners[evt] || []; listeners[evt].push(fn); }},
                removeEventListener: (evt, fn) => {{
                    if (listeners[evt]) listeners[evt] = listeners[evt].filter(f => f !== fn);
                }},
                dispatchEvent: (evt) => {{
                    (listeners[evt.type] || []).forEach(f => f(evt));
                    return true;
                }},
                getBoundingClientRect: () => ({{ width: 300, height: 200, top: 0, left: 0 }})
            }};
            return element;
        }}

        const mockCanvas = createMockDOM();
        mockCanvas.tagName = 'CANVAS'; mockCanvas.width = 300; mockCanvas.height = 200;
        const mockCtx = {{
            clearRect: () => {{}}, beginPath: () => {{}}, arc: () => {{}}, stroke: () => {{}},
            fill: () => {{}}, save: () => {{}}, restore: () => {{}}, setLineDash: () => {{}},
            strokeStyle: '#000', fillStyle: '#000', lineWidth: 1
        }};
        mockCanvas.getContext = (type) => (type === '2d' ? mockCtx : null);

        const mockDocument = {{
            createElement: (tag) => {{
                if (tag.toLowerCase() === 'canvas') return mockCanvas;
                return createMockDOM();
            }},
            addEventListener: () => {{}},
            removeEventListener: () => {{}}
        }};

        let rafId = 0;
        let cancelledRafs = [];
        const mockWindow = {{
            document: mockDocument,
            requestAnimationFrame: (cb) => {{ rafId++; return rafId; }},
            cancelAnimationFrame: (id) => {{ cancelledRafs.push(id); }},
            addEventListener: () => {{}},
            removeEventListener: () => {{}}
        }};

        let code = fs.readFileSync('{AVATAR_JS_PATH}', 'utf-8');
        code = code.replace(/export\\s+const\\s+/g, 'const ');
        code = code.replace(/export\\s+function\\s+/g, 'function ');
        code = code.replace(/export\\s+class\\s+/g, 'class ');
        code = code.replace(/export\\s+default\\s+/g, '');

        const sandbox = {{
            window: mockWindow,
            document: mockDocument,
            requestAnimationFrame: mockWindow.requestAnimationFrame,
            cancelAnimationFrame: mockWindow.cancelAnimationFrame,
            console,
            CustomEvent: class {{ constructor(type, detail) {{ this.type = type; this.detail = detail?.detail; }} }},
            Math
        }};

        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);

        const TacticalAvatar3D = sandbox.TacticalAvatar3D || sandbox.window.TacticalAvatar3D;
        const avatar3D = sandbox.avatar3D || sandbox.window.avatar3D || (TacticalAvatar3D ? new TacticalAvatar3D() : null);

        if (!avatar3D) throw new Error('TacticalAvatar3D ou avatar3D não exportado');

        // 1. Inicialização com container element
        const container = createMockDOM();
        avatar3D.init(container, {{ width: 300, height: 200 }});
        if (avatar3D.getState() !== 'IDLE' && avatar3D.getState() !== 'READY') {{
            throw new Error('Estado inicial inválido: ' + avatar3D.getState());
        }}

        // 2. Transição para todos os estados esperados
        const states = ['LISTENING', 'THINKING', 'DISPATCHING_WORKER', 'TESTING', 'SPEAKING'];
        for (const st of states) {{
            avatar3D.setState(st, {{ reason: 'test-' + st.toLowerCase() }});
            if (avatar3D.getState() !== st) {{
                throw new Error('Falha ao definir estado: esperado ' + st + ', recebido ' + avatar3D.getState());
            }}
            if (container.dataset.state !== st) {{
                throw new Error('container.dataset.state não reflete o estado ' + st);
            }}
        }}

        // 3. Reatividade a áudio
        avatar3D.updateAudioLevel(0.75);
        if (typeof avatar3D.getAudioLevel === 'function') {{
            if (Math.abs(avatar3D.getAudioLevel() - 0.75) > 0.001) {{
                throw new Error('getAudioLevel não retornou o RMS correto');
            }}
        }}
        // Clamping de áudio negativo e excessivo
        avatar3D.updateAudioLevel(-0.5);
        if (typeof avatar3D.getAudioLevel === 'function' && avatar3D.getAudioLevel() < 0) {{
            throw new Error('updateAudioLevel permitiu RMS negativo');
        }}
        avatar3D.updateAudioLevel(2.5);
        if (typeof avatar3D.getAudioLevel === 'function' && avatar3D.getAudioLevel() > 1) {{
            throw new Error('updateAudioLevel não limitou RMS a 1.0');
        }}

        // 4. Destruição e Cleanup
        avatar3D.destroy();
        if (cancelledRafs.length === 0) {{
            throw new Error('destroy() não cancelou animação via cancelAnimationFrame');
        }}

        console.log(JSON.stringify({{ success: true }}));
        """

        proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
        self.assertEqual(
            proc.returncode,
            0,
            f"Falha na validação Node.js de avatar_3d.js:\nStdout: {proc.stdout}\nStderr: {proc.stderr}"
        )
        self.assertIn('"success":true', proc.stdout)

    def test_06_threejs_procedural_integration(self):
        """Valida que quando THREE está presente, avatar_3d.js inicializa cena 3D proceduralmente sem assets externos."""
        node_script = f"""
        const fs = require('fs');
        const vm = require('vm');

        let createdMeshes = [];
        let createdGeometries = [];
        let createdMaterials = [];

        const mockThree = {{
            Scene: class {{ constructor() {{ this.children = []; }} add(obj) {{ this.children.push(obj); }} }},
            PerspectiveCamera: class {{
                constructor(fov, aspect, near, far) {{ this.position = {{ x: 0, y: 0, z: 0, set(x,y,z){{ this.x=x;this.y=y;this.z=z; }} }}; }}
            }},
            WebGLRenderer: class {{
                constructor(opts) {{
                    this.domElement = {{ tagName: 'CANVAS', style: {{}} }};
                }}
                setSize(w, h) {{ this.width = w; this.height = h; }}
                setPixelRatio() {{}}
                setClearColor() {{}}
                render() {{}}
                dispose() {{ this.disposed = true; }}
            }},
            IcosahedronGeometry: class {{
                constructor(radius, detail) {{ this.radius = radius; this.detail = detail; createdGeometries.push('IcosahedronGeometry'); }}
                dispose() {{}}
            }},
            SphereGeometry: class {{
                constructor(r) {{ this.r = r; createdGeometries.push('SphereGeometry'); }}
                dispose() {{}}
            }},
            TorusGeometry: class {{
                constructor(r, t, rad, seg) {{ createdGeometries.push('TorusGeometry'); }}
                dispose() {{}}
            }},
            BufferGeometry: class {{
                constructor() {{ createdGeometries.push('BufferGeometry'); }}
                setAttribute() {{}}
                dispose() {{}}
            }},
            Float32BufferAttribute: class {{ constructor() {{}} }},
            Points: class {{
                constructor(geom, mat) {{
                    this.geometry = geom; this.material = mat;
                    this.rotation = {{ x: 0, y: 0, z: 0 }};
                    this.scale = {{ x: 1, y: 1, z: 1, setScalar(s){{ this.x=s;this.y=s;this.z=s; }} }};
                    createdMeshes.push(this);
                }}
            }},
            Mesh: class {{
                constructor(geom, mat) {{
                    this.geometry = geom; this.material = mat;
                    this.rotation = {{ x: 0, y: 0, z: 0 }};
                    this.scale = {{ x: 1, y: 1, z: 1, setScalar(s){{ this.x=s;this.y=s;this.z=s; }} }};
                    createdMeshes.push(this);
                }}
            }},
            MeshBasicMaterial: class {{ constructor(opts) {{ this.opts = opts; createdMaterials.push('MeshBasicMaterial'); }} dispose() {{}} }},
            PointsMaterial: class {{ constructor(opts) {{ this.opts = opts; createdMaterials.push('PointsMaterial'); }} dispose() {{}} }},
            ShaderMaterial: class {{ constructor(opts) {{ this.opts = opts; createdMaterials.push('ShaderMaterial'); }} dispose() {{}} }},
            Color: class {{ constructor(c) {{ this.color = c; }} setHex(h) {{ this.color = h; }} }}
        }};

        function createMockDOM() {{
            return {{
                tagName: 'DIV',
                classList: {{ add: () => {{}}, remove: () => {{}}, contains: () => false }},
                attributes: {{}},
                dataset: {{}},
                style: {{}},
                children: [],
                childNodes: [],
                appendChild: (c) => c,
                removeChild: (c) => c,
                setAttribute: () => {{}},
                getAttribute: () => null,
                addEventListener: () => {{}},
                removeEventListener: () => {{}},
                dispatchEvent: () => true,
                getBoundingClientRect: () => ({{ width: 400, height: 300 }})
            }};
        }}

        const mockWindow = {{
            THREE: mockThree,
            document: {{ createElement: () => createMockDOM(), addEventListener: () => {{}}, removeEventListener: () => {{}} }},
            requestAnimationFrame: () => 1,
            cancelAnimationFrame: () => {{}},
            addEventListener: () => {{}},
            removeEventListener: () => {{}}
        }};

        let code = fs.readFileSync('{AVATAR_JS_PATH}', 'utf-8');
        code = code.replace(/export\\s+const\\s+/g, 'const ');
        code = code.replace(/export\\s+function\\s+/g, 'function ');
        code = code.replace(/export\\s+class\\s+/g, 'class ');
        code = code.replace(/export\\s+default\\s+/g, '');

        const sandbox = {{
            window: mockWindow,
            document: mockWindow.document,
            requestAnimationFrame: mockWindow.requestAnimationFrame,
            cancelAnimationFrame: mockWindow.cancelAnimationFrame,
            THREE: mockThree,
            console,
            CustomEvent: class {{ constructor(t, d) {{ this.type = t; this.detail = d; }} }}
        }};

        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);

        const TacticalAvatar3D = sandbox.TacticalAvatar3D || sandbox.window.TacticalAvatar3D;
        const avatar = new TacticalAvatar3D();
        avatar.init(createMockDOM());

        if (createdGeometries.length === 0) {{
            throw new Error('Nenhuma geometria procedural foi criada no modo Three.js');
        }}

        avatar.setState('LISTENING');
        avatar.updateAudioLevel(0.9);
        avatar.setState('DISPATCHING_WORKER');
        avatar.destroy();

        console.log(JSON.stringify({{ success: true, geometries: createdGeometries.length, meshes: createdMeshes.length }}));
        """

        proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
        self.assertEqual(
            proc.returncode,
            0,
            f"Falha na validação Three.js de avatar_3d.js:\nStdout: {proc.stdout}\nStderr: {proc.stderr}"
        )
        self.assertIn('"success":true', proc.stdout)


if __name__ == "__main__":
    unittest.main()
