import os
import re
import unittest
import subprocess

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR = os.path.join(BASE_DIR, "web")
JS_DIR = os.path.join(WEB_DIR, "js")
STATE_JS_PATH = os.path.join(JS_DIR, "state.js")
CODEBASE_GRAPH_JS_PATH = os.path.join(JS_DIR, "codebase_graph.js")
TERMINAL_WORKSPACE_JS_PATH = os.path.join(JS_DIR, "terminal_workspace.js")
INDEX_HTML_PATH = os.path.join(WEB_DIR, "index.html")

class TestIssue23CleanupAndCanonicalRoot(unittest.TestCase):
    """
    Testes de conformidade para a Issue #23 (Fatia 3):
    - getActiveProjectRoot canônica em state.js
    - codebase_graph.js e terminal_workspace.js utilizam getActiveProjectRoot de state.js
    - Remoção da seção morta #view-settings de index.html
    """

    def setUp(self):
        with open(STATE_JS_PATH, "r", encoding="utf-8") as f:
            self.state_js = f.read()
        with open(CODEBASE_GRAPH_JS_PATH, "r", encoding="utf-8") as f:
            self.codebase_graph_js = f.read()
        with open(TERMINAL_WORKSPACE_JS_PATH, "r", encoding="utf-8") as f:
            self.terminal_workspace_js = f.read()
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            self.index_html = f.read()

    def test_state_js_exports_get_active_project_root(self):
        """Verifica se web/js/state.js declara e exporta getActiveProjectRoot(projectId, projectsMap)."""
        export_pattern = r'export\s+function\s+getActiveProjectRoot\s*\('
        self.assertRegex(
            self.state_js,
            export_pattern,
            "web/js/state.js deve exportar a função getActiveProjectRoot"
        )

    def test_state_js_get_active_project_root_behavior(self):
        """Executa via Node.js para validar a lógica de getActiveProjectRoot(projectId, projectsMap)."""
        node_script = """
        import { getActiveProjectRoot, setKnownProjects, setCurrentProjectId, setState } from './web/js/state.js';
        import assert from 'assert';

        // 1. Consulta passando projectId e projectsMap (array)
        const mockList = [
          { id: 'proj-1', project_root: '/tmp/proj1' },
          { id: 'proj-2', project_root: '/tmp/proj2' }
        ];
        assert.strictEqual(getActiveProjectRoot('proj-1', mockList), '/tmp/proj1');
        assert.strictEqual(getActiveProjectRoot('proj-2', mockList), '/tmp/proj2');

        // 2. Consulta com projectsMap como objeto/dicionário
        const mockMap = {
          'p-alpha': { project_root: '/tmp/alpha' },
          'p-beta': { project_root: '/tmp/beta' }
        };
        assert.strictEqual(getActiveProjectRoot('p-alpha', mockMap), '/tmp/alpha');

        // 3. Consulta com fallback para estado reativo
        setKnownProjects(mockList);
        setCurrentProjectId('proj-2');
        assert.strictEqual(getActiveProjectRoot(), '/tmp/proj2');

        // 4. Fallback para state.project_root se não encontrado na lista
        setCurrentProjectId('unknown-id');
        setState({ project_root: '/fallback/root' });
        assert.strictEqual(getActiveProjectRoot(), '/fallback/root');

        // 5. Retorna string vazia quando nada configurado
        setState({});
        setKnownProjects([]);
        assert.strictEqual(getActiveProjectRoot('non-existent', []), '');

        console.log("ALL_STATE_ASSERTIONS_PASSED");
        """
        result = subprocess.run(
            ["node", "--input-type=module", "-e", node_script],
            cwd=BASE_DIR,
            capture_output=True,
            text=True
        )
        self.assertEqual(
            result.returncode, 0,
            f"Erro na execução da lógica de getActiveProjectRoot em Node: {result.stderr}"
        )
        self.assertIn("ALL_STATE_ASSERTIONS_PASSED", result.stdout)

    def test_codebase_graph_uses_state_get_active_project_root(self):
        """web/js/codebase_graph.js deve importar getActiveProjectRoot de ./state.js e não duplicar a lógica."""
        import_match = re.search(
            r'import\s+\{[^}]*getActiveProjectRoot[^}]*\}\s+from\s+[\'"]\./state\.js[\'"]',
            self.codebase_graph_js
        )
        self.assertTrue(
            import_match,
            "web/js/codebase_graph.js deve importar getActiveProjectRoot de ./state.js"
        )
        # Não deve haver declaração de função duplicada interna com lógica própria
        duplicate_decl = re.findall(
            r'function\s+getActiveProjectRoot\s*\([^)]*\)\s*\{',
            self.codebase_graph_js
        )
        self.assertEqual(
            len(duplicate_decl), 0,
            "web/js/codebase_graph.js não deve declarar sua própria função getActiveProjectRoot duplicada"
        )

    def test_terminal_workspace_uses_state_get_active_project_root(self):
        """web/js/terminal_workspace.js deve importar getActiveProjectRoot de ./state.js e delegar a ela."""
        import_match = re.search(
            r'import\s+\{[^}]*getActiveProjectRoot[^}]*\}\s+from\s+[\'"]\./state\.js[\'"]',
            self.terminal_workspace_js
        )
        self.assertTrue(
            import_match,
            "web/js/terminal_workspace.js deve importar getActiveProjectRoot de ./state.js"
        )
        # Verifica se getActiveProjectRoot() no manager delega para a função canônica
        self.assertIn(
            "getActiveProjectRoot(",
            self.terminal_workspace_js,
            "web/js/terminal_workspace.js deve invocar getActiveProjectRoot"
        )
        # Certifica-se de que a implementação interna duplicada divergente foi substituída
        self.assertNotIn(
            "state.config && state.config.project_root",
            self.terminal_workspace_js,
            "Lógica divergente legada (state.config.project_root) deve ser unificada em getActiveProjectRoot"
        )

    def test_dead_view_settings_removed_from_index_html(self):
        """A seção/container duplicado e morto #view-settings deve ser completamente removido do index.html."""
        self.assertNotRegex(
            self.index_html,
            r'<section[^>]*id=["\']view-settings["\']',
            "A seção legada <section id='view-settings'> deve ser removida de web/index.html"
        )
        self.assertNotRegex(
            self.index_html,
            r'<div[^>]*id=["\']view-settings["\']',
            "Qualquer <div id='view-settings'> deve ser removida de web/index.html"
        )

if __name__ == "__main__":
    unittest.main()
