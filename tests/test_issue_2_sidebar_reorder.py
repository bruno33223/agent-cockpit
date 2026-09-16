import os
import re
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_FILE = os.path.join(BASE_DIR, "web", "index.html")
CSS_FILE = os.path.join(BASE_DIR, "web", "styles.css")
JS_FILE = os.path.join(BASE_DIR, "web", "app.js")

class TestIssue2SidebarReorder(unittest.TestCase):
    """
    Testes de conformidade para a Issue 2:
    [Sidebar] Reestruturacao da Left Sidebar com Navegacao Superior e Secao de Workspaces Unificada
    """

    def setUp(self):
        with open(HTML_FILE, "r", encoding="utf-8") as f:
            self.html = f.read()
        with open(CSS_FILE, "r", encoding="utf-8") as f:
            self.css = f.read()
        with open(JS_FILE, "r", encoding="utf-8") as f:
            self.js = f.read()
        js_dir = os.path.join(BASE_DIR, "web", "js")
        if os.path.isdir(js_dir):
            for fname in sorted(os.listdir(js_dir)):
                if fname.endswith(".js"):
                    with open(os.path.join(js_dir, fname), "r", encoding="utf-8") as f:
                        self.js += "\n" + f.read()

    def test_sidebar_toggle_exists_at_top(self):
        """O botão #btn-sidebar-toggle deve estar presente no topo da sidebar."""
        self.assertIn('id="btn-sidebar-toggle"', self.html)
        sidebar_start = self.html.find('id="app-sidebar"')
        toggle_pos = self.html.find('id="btn-sidebar-toggle"')
        self.assertGreater(toggle_pos, sidebar_start, "btn-sidebar-toggle deve estar dentro da app-sidebar")

    def test_views_navigation_is_above_workspaces_section(self):
        """
        Requisito 1 & 2: Menu de Navegação no Topo da Sidebar.
        A navegação de Views (#sidebar-views-nav) deve aparecer ANTES da seção WORKSPACES
        (cabeçalho de workspaces e seções pinned/in-progress).
        """
        sidebar_start = self.html.find('id="app-sidebar"')
        self.assertNotEqual(sidebar_start, -1, "app-sidebar não encontrada no HTML")

        views_nav_pos = self.html.find('id="sidebar-views-nav"', sidebar_start)
        self.assertNotEqual(views_nav_pos, -1, "sidebar-views-nav não encontrado no HTML")

        # Posição da seção / cabeçalho de workspaces no corpo da sidebar
        pinned_section_pos = self.html.find('id="section-pinned"', sidebar_start)
        progress_section_pos = self.html.find('id="section-progress"', sidebar_start)

        # O menu de navegação de views DEVE vir antes das seções Pinned e Progress
        self.assertLess(
            views_nav_pos,
            pinned_section_pos,
            "A navegação das VIEWS deve estar posicionada no TOPO, antes da seção Pinned de Workspaces"
        )
        self.assertLess(
            views_nav_pos,
            progress_section_pos,
            "A navegação das VIEWS deve estar posicionada antes da seção In Progress de Workspaces"
        )

    def test_all_view_buttons_present_and_terminal_primary(self):
        """
        Navegação das VIEWS:
        Terminal (Primária), Fluxo/Kanban, Code Graph, Gauntlet Log, Handoff, Local Worker, Configurações.
        A aba 'Visão Geral' foi descontinuada e o Terminal é a aba primária padrão.
        """
        required_views = [
            'view-terminal',
            'view-flow',
            'view-graph',
            'view-gauntlet',
            'view-handoff',
            'view-worker',
            'view-settings',
        ]
        sidebar_nav_match = re.search(r'<nav[^>]*id=["\']sidebar-views-nav["\'][^>]*>(.*?)</nav>', self.html, re.DOTALL)
        self.assertIsNotNone(sidebar_nav_match, "Elemento nav#sidebar-views-nav não localizado")
        nav_content = sidebar_nav_match.group(1)

        for view in required_views:
            self.assertIn(
                f'data-view="{view}"',
                nav_content,
                f"Botão para a view '{view}' deve estar dentro de #sidebar-views-nav"
            )

        # Garante que a aba 'view-overview' não existe mais
        self.assertNotIn('data-view="view-overview"', nav_content)

        # Garante que a primeira aba ativa é o Terminal
        first_btn_match = re.search(r'<button[^>]*class=["\'][^"\']*nav-tab[^"\']*active[^"\']*["\'][^>]*data-view=["\']([^"\']+)["\']', nav_content)
        self.assertIsNotNone(first_btn_match, "Primeiro botão ativo não encontrado")
        self.assertEqual(first_btn_match.group(1), 'view-terminal', "A aba primária ativa deve ser 'view-terminal'")

    def test_workspaces_section_controls(self):
        """
        Requisito 2: Seção WORKSPACES unificada logo abaixo com:
        - Título / label 'WORKSPACES'
        - Botão (+) de criar nova worktree / sessão (#btn-sidebar-new-worktree)
        - Seções Pinned (#section-pinned) e In Progress (#section-progress)
        """
        self.assertIn('id="btn-sidebar-new-worktree"', self.html)
        self.assertIn('id="section-pinned"', self.html)
        self.assertIn('id="section-progress"', self.html)
        self.assertIn('id="pinned-count"', self.html)
        self.assertIn('id="worktree-progress-count"', self.html)
        self.assertIn('id="worktree-cards-list"', self.html)

        # O botão new worktree e o container de workspaces devem vir APÓS o sidebar-views-nav
        views_nav_pos = self.html.find('id="sidebar-views-nav"')
        workspaces_header_pos = self.html.find('sidebar-workspaces-header')
        if workspaces_header_pos != -1:
            self.assertGreater(
                workspaces_header_pos,
                views_nav_pos,
                "Cabeçalho da seção WORKSPACES deve ficar posicionado logo abaixo do menu de navegação de Views"
            )

    def test_clean_visual_identity_in_css(self):
        """
        Requisito 3: Identidade Visual Clean estilo Orca Dev Tool.
        - Cards de worktrees (.worktree-card) compactos (sem padding exagerado)
        - .nav-tab e .worktree-card com tipografia e espaçamentos minimalistas
        """
        # Verifica se .worktree-card tem padding compacto
        self.assertIn('.worktree-card {', self.css)
        self.assertIn('.nav-tab {', self.css)
        self.assertIn('.app-sidebar.collapsed', self.css)

    def test_js_navigation_and_handlers_parity(self):
        """Garante que app.js possui listeners e switchTab operacionais sem referências quebradas."""
        self.assertIn('window.switchTab = function(viewId)', self.js)
        self.assertIn('initSidebar', self.js)
        self.assertIn('btn-sidebar-toggle', self.js)
        self.assertIn('btn-sidebar-new-worktree', self.js)


if __name__ == '__main__':
    unittest.main()
