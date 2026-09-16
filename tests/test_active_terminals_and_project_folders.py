import unittest
import os
import tempfile
import shutil
from server.state_store import StateStore, canonical_project_id

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(BASE_DIR, "web", "index.html")
STYLES_CSS = os.path.join(BASE_DIR, "web", "styles.css")
TERMINAL_JS = os.path.join(BASE_DIR, "web", "js", "terminal_workspace.js")
SETTINGS_JS = os.path.join(BASE_DIR, "web", "js", "settings.js")
SIDEBAR_JS = os.path.join(BASE_DIR, "web", "js", "sidebar.js")

class TestActiveTerminalsAndProjectFolders(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store = StateStore(states_dir=self.temp_dir)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_project_uniqueness_by_folder(self):
        """Valida que múltiplos registros para a mesma pasta física são deduplicados para uma entrada única."""
        folder_a = os.path.join(self.temp_dir, "projeto_alpha")
        os.makedirs(folder_a, exist_ok=True)

        state_1 = {"epic": {"name": "Projeto Alpha"}, "project_root": folder_a, "nodes": []}
        self.store._save_state(state_1, "alpha-1")

        state_2 = {"epic": {"name": "Projeto Alpha Refatorado"}, "project_root": folder_a, "nodes": []}
        self.store._save_state(state_2, "alpha-2")

        projects = self.store.list_projects()
        alpha_projects = [p for p in projects if p.get("project_root") == os.path.realpath(folder_a)]
        self.assertEqual(len(alpha_projects), 1, "Não devem existir múltiplos projetos para a mesma pasta")
        self.assertEqual(alpha_projects[0]["name"], "projeto_alpha")

    def test_terminal_ui_elements_in_html(self):
        """Valida presença do botão e modal de terminais ativos e remoção de botões da sidebar."""
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            html = f.read()

        # Botão de ver terminais ativos e badge de contagem
        self.assertIn('id="btn-active-terminals"', html)
        self.assertIn('id="active-terminals-count"', html)

        # Modal de terminais ativos
        self.assertIn('id="modal-active-terminals"', html)
        self.assertIn('id="active-terminals-list"', html)
        self.assertIn('id="btn-active-terminals-show-all"', html)
        self.assertIn('id="btn-active-terminals-hide-all"', html)

        # Controles de Autostart e Gate nas Configurações
        self.assertIn('id="ag-btn-autostart-on"', html)
        self.assertIn('id="ag-btn-autostart-off"', html)
        self.assertIn('id="ag-gate-badge"', html)
        self.assertIn('id="btn-ag-approve-gate"', html)

        # Sidebar footer limpo: botões isolados de autostart e gate removidos da sidebar
        self.assertNotIn('id="btn-autostart"', html)
        self.assertNotIn('id="btn-human-gate"', html)

    def test_terminal_workspace_js_has_minimize_and_active_management(self):
        """Valida métodos e listeners de minimização e gestão de visibilidade no JS."""
        with open(TERMINAL_JS, "r", encoding="utf-8") as f:
            js = f.read()

        self.assertIn('orca-btn-minimize', js)
        self.assertIn('minimizeSession', js)
        self.assertIn('restoreSession', js)
        self.assertIn('toggleSessionVisibility', js)
        self.assertIn('getProjectSessions', js)
        self.assertIn('openActiveTerminalsModal', js)

    def test_settings_js_has_functional_autostart_and_gate_handlers(self):
        """Valida que settings.js possui handlers reais para autostart e aprovação de gate."""
        with open(SETTINGS_JS, "r", encoding="utf-8") as f:
            js = f.read()

        self.assertIn('setSystemAutostart', js)
        self.assertIn('updateHumanGateUI', js)
        self.assertIn('approveHumanGate', js)
    def test_terminal_is_primary_tab_and_overview_removed(self):
        """Valida que o Terminal é a aba primária ativa do sistema e que Visão Geral foi removida."""
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            html = f.read()

        # Garante que a view-overview foi removida da navegação e das sections
        self.assertNotIn('data-view="view-overview"', html)
        self.assertNotIn('id="view-overview"', html)

        # Garante que view-terminal é a aba ativa primária
        self.assertIn('class="nav-tab active" data-view="view-terminal"', html)
        self.assertIn('class="tab-view active" id="view-terminal"', html)

if __name__ == "__main__":
    unittest.main()
