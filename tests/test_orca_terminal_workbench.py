import unittest
import os

class TestOrcaTerminalWorkbench(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.html_path = os.path.join(self.base_dir, 'web', 'index.html')
        self.js_path = os.path.join(self.base_dir, 'web', 'app.js')
        self.css_path = os.path.join(self.base_dir, 'web', 'styles.css')

        with open(self.html_path, 'r', encoding='utf-8') as f:
            self.html_content = f.read()
        with open(self.js_path, 'r', encoding='utf-8') as f:
            self.js_content = f.read()
        js_dir = os.path.join(self.base_dir, 'web', 'js')
        if os.path.isdir(js_dir):
            for fname in sorted(os.listdir(js_dir)):
                if fname.endswith('.js'):
                    with open(os.path.join(js_dir, fname), 'r', encoding='utf-8') as f:
                        self.js_content += '\n' + f.read()
        with open(self.css_path, 'r', encoding='utf-8') as f:
            self.css_content = f.read()

    def test_index_html_view_terminal_structure(self):
        self.assertIn('id="view-terminal"', self.html_content)
        self.assertIn('terminal-layout-picker', self.html_content)
        self.assertIn('data-layout="tabs"', self.html_content)
        self.assertIn('data-layout="split"', self.html_content)
        self.assertIn('data-layout="grid"', self.html_content)
        self.assertIn('id="btn-toggle-sidebar"', self.html_content)
        self.assertIn('id="btn-new-terminal"', self.html_content)
        self.assertIn('id="btn-run-opencode"', self.html_content)
        self.assertIn('id="btn-run-claude"', self.html_content)
        self.assertIn('id="terminal-tabs-bar"', self.html_content)
        self.assertIn('id="terminal-workspace-grid"', self.html_content)

    def test_app_js_orca_pane_header_and_tabs(self):
        self.assertIn('orca-pane-header', self.js_content)
        self.assertIn('orca-tab-strip', self.js_content)
        self.assertIn('orca-tab-icon', self.js_content)
        self.assertIn('orca-tab-title', self.js_content)

    def test_app_js_orca_pane_controls(self):
        self.assertIn('orca-pane-controls', self.js_content)
        self.assertIn('orca-btn-close', self.js_content)
        # Issue #10: split, clear e restart removidos em prol de cabeçalho limpo com apenas botão fechar
        self.assertNotIn('orca-btn-split', self.js_content)
        self.assertNotIn('orca-btn-clear', self.js_content)
        self.assertNotIn('orca-btn-restart', self.js_content)

    def test_app_js_orca_terminal_statusline(self):
        # Issue #10: statusline redundante foi limpa, mantendo permissões nos helpers e telemetria live
        self.assertIn('bypass permissions on (shift+tab to cycle) - for agents', self.js_content)
        self.assertIn('MCP Live', self.html_content)

    def test_app_js_agent_type_switching(self):
        self.assertIn('orca-agent-select', self.js_content)
        self.assertIn('setSessionAgent', self.js_content)
        self.assertIn('Claude Code', self.js_content)
        self.assertIn('OpenCode', self.js_content)
        self.assertIn('getAgentCommand', self.js_content)

    def test_app_js_resize_and_pty_robustness(self):
        self.assertIn('ResizeObserver', self.js_content)
        self.assertIn('fitAddon.fit()', self.js_content)
        self.assertIn('ws/terminal', self.js_content)
        self.assertIn('closeSession', self.js_content)
        self.assertIn('splitSession', self.js_content)

    def test_styles_css_orca_rules(self):
        self.assertIn('.orca-tab-strip', self.css_content)
        self.assertIn('.orca-tab', self.css_content)
        self.assertIn('.orca-tab.active', self.css_content)
        self.assertIn('.orca-pane-header', self.css_content)
        self.assertIn('.orca-pane-subtitle', self.css_content)
        self.assertIn('.orca-terminal-statusline', self.css_content)
        self.assertIn('.orca-agent-select', self.css_content)
        self.assertIn('.orca-pane-btn', self.css_content)
        self.assertIn('.orca-agent-claude', self.css_content)
        self.assertIn('.orca-agent-opencode', self.css_content)
        self.assertIn('.orca-status-mcp-indicator', self.css_content)

if __name__ == "__main__":
    unittest.main()
