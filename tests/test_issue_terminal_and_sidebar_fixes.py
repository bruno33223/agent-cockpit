import unittest
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_JS_PATH = os.path.join(BASE_DIR, "web", "app.js")
STYLES_CSS_PATH = os.path.join(BASE_DIR, "web", "styles.css")

class TestTerminalAndSidebarFixes(unittest.TestCase):
    def setUp(self):
        with open(APP_JS_PATH, "r", encoding="utf-8") as f:
            self.js = f.read()
        js_dir = os.path.join(BASE_DIR, "web", "js")
        if os.path.isdir(js_dir):
            for fname in sorted(os.listdir(js_dir)):
                if fname.endswith(".js"):
                    with open(os.path.join(js_dir, fname), "r", encoding="utf-8") as f:
                        self.js += "\n" + f.read()
        with open(STYLES_CSS_PATH, "r", encoding="utf-8") as f:
            self.css = f.read()

    def test_terminal_tabsbar_defensive_lookup_in_create_session(self):
        """Valida que createSession busca tabsBar e gridContainer defensivamente caso ainda não inicializados."""
        self.assertIn("this.tabsBar = document.getElementById('terminal-tabs-bar')", self.js)
        self.assertIn("this.gridContainer = document.getElementById('terminal-workspace-grid')", self.js)

    def test_terminal_init_called_on_app_startup(self):
        """Valida que terminalWorkspace.init() é chamado na inicialização da aplicação."""
        self.assertIn("terminalWorkspace.init()", self.js)

    def test_styles_css_does_not_hide_higher_index_terminals(self):
        """Valida que o CSS não oculta terminais a partir do 3º ou 5º filho com nth-child(n+5)."""
        self.assertNotIn(".terminal-pane:nth-child(n+5)", self.css)
        self.assertNotIn(".terminal-pane:nth-child(n+3)", self.css)

    def test_pinned_projects_does_not_auto_pin_current_project(self):
        """Valida que selecionar um projeto não o torna automaticamente pinned."""
        self.assertNotIn("pinnedProjects.push(fallback)", self.js)
        self.assertNotIn("return currentProjectId ? [currentProjectId] : ['default']", self.js)

    def test_projects_list_does_not_render_slices_nodes(self):
        """Valida que a lista de projetos na sidebar não renderiza nós de fatias verticais (SLICE-X)."""
        self.assertNotIn("nodes.forEach(node => {", self.js)

    def test_switch_project_does_not_reorder_recent_projects(self):
        """Valida que navegar/clicar no projeto não reordena a lista (não chama recordRecentProject no switch/render)."""
        # switchProject não deve chamar recordRecentProject
        switch_func = self.js[self.js.find("async function switchProject"):self.js.find("async function switchProject") + 400]
        self.assertNotIn("recordRecentProject(currentProjectId)", switch_func)
        # renderWorktreeSidebar não deve chamar recordRecentProject
        render_func = self.js[self.js.find("function renderWorktreeSidebar"):self.js.find("function renderWorktreeSidebar") + 400]
        self.assertNotIn("recordRecentProject(currentProjectId)", render_func)

    def test_agent_state_dot_logic_in_app_js(self):
        """Valida a lógica da função helper getProjectDotClass e uso na renderização de cards."""
        self.assertIn("function getProjectDotClass(proj)", self.js)
        self.assertIn("function getProjectDotTitle(dotClass)", self.js)
        self.assertIn("const dotClass = getProjectDotClass(proj);", self.js)
        # Deve checar done primeiro
        self.assertIn("if (proj.total_slices > 0 && proj.approved_slices === proj.total_slices)", self.js)
        # Não deve marcar cegamente working se total_slices > 0
        self.assertNotIn("const dotClass = isDone ? 'done' : (proj.total_slices > 0 ? 'working' : 'idle');", self.js)

    def test_record_recent_project_on_user_actions(self):
        """Valida que recordRecentProject é acionado por comandos no terminal ou criação de terminal."""
        # 1. Entrada de comando no terminal (Enter)
        self.assertIn("recordRecentProject(pid)", self.js)
        # 2. Ao clicar no botão de novo terminal ou aba +
        self.assertIn("btnAddTab.addEventListener('click', () => {", self.js)
        # 3. Ao enviar comando para sessão
        send_to_session_block = self.js[self.js.find("sendToSession(sessionId, cmd) {"):self.js.find("sendToSession(sessionId, cmd) {") + 300]
        self.assertIn("recordRecentProject(pid)", send_to_session_block)

    def test_state_store_includes_active_agents_and_waiting_user(self):
        """Valida que o backend StateStore persiste e retorna active_agents e waiting_user na listagem."""
        from server.state_store import StateStore
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = StateStore(states_dir=tmpdir)
            # Cria projeto com nós executando
            state_data = {
                "epic": {"name": "Test Epic", "status": "IN_PROGRESS"},
                "nodes": [
                    {"id": "s1", "title": "Slice 1", "kanban_status": "EXECUTING"}
                ],
                "pairs_3x3": []
            }
            store._update_index_entry("p1", "Project 1", "/tmp/p1", state_data)
            projects = store.list_projects()
            p1 = next(p for p in projects if p["id"] == "p1")
            self.assertEqual(p1["active_agents"], 1)
            self.assertFalse(p1["waiting_user"])

            # Atualiza projeto para aguardando validação
            state_data_waiting = {
                "epic": {"name": "Test Epic", "status": "IN_PROGRESS"},
                "nodes": [
                    {"id": "s1", "title": "Slice 1", "kanban_status": "WAITING_REVIEW"}
                ],
                "pairs_3x3": []
            }
            store._update_index_entry("p1", "Project 1", "/tmp/p1", state_data_waiting)
            projects = store.list_projects()
            p1_updated = next(p for p in projects if p["id"] == "p1")
            self.assertEqual(p1_updated["active_agents"], 0)
            self.assertTrue(p1_updated["waiting_user"])

    def test_agent_state_dot_colors_spec(self):
        """Valida cores exatas: cinza (idle), azul (working), laranja (waiting/validação), verde (done)."""
        self.assertIn(".agent-state-dot.working {\n  background-color: #3b82f6", self.css)
        self.assertIn(".agent-state-dot.done {\n  background-color: #10b981", self.css)
        self.assertIn(".agent-state-dot.waiting", self.css)
        self.assertIn("background-color: #f97316", self.css)
        self.assertIn(".agent-state-dot.idle {\n  background-color: #52525b", self.css)

if __name__ == "__main__":
    unittest.main()
