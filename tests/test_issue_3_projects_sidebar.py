import os
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_FILE = os.path.join(BASE_DIR, "web", "index.html")
CSS_FILE = os.path.join(BASE_DIR, "web", "styles.css")
JS_FILE = os.path.join(BASE_DIR, "web", "app.js")

class TestIssue3ProjectsSidebar(unittest.TestCase):
    """
    Testes de conformidade para a Issue 3:
    [Workspaces] Gerenciamento de Projetos na Sidebar: Secao Pinned e Lista Projects com 'Exibir Mais'
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

    def test_dropdown_removed_from_titlebar_html(self):
        """
        Requisito 1: Eliminar Dropdown do Topo.
        A Titlebar não deve conter o seletor visual de projeto (.project-selector-wrapper).
        """
        titlebar_start = self.html.find('id="orca-titlebar"')
        titlebar_end = self.html.find('</header>', titlebar_start)
        titlebar_html = self.html[titlebar_start:titlebar_end]

        self.assertNotIn(
            'class="project-selector-wrapper"',
            titlebar_html,
            "project-selector-wrapper deve ser removido da titlebar superior"
        )

    def test_sidebar_has_pinned_and_projects_sections(self):
        """
        Requisito 2 & 3: Sidebar deve possuir seção Pinned e seção de Projetos (Recentes/Geral).
        """
        self.assertIn('id="section-pinned"', self.html, "Seção Pinned deve existir na sidebar")
        self.assertIn('id="worktree-pinned-list"', self.html, "Container da lista Pinned deve existir")
        self.assertIn('id="pinned-count"', self.html, "Contador de Pinned deve existir")

        # Container para projetos recentes / gerais
        self.assertTrue(
            ('id="worktree-cards-list"' in self.html) or ('id="projects-cards-list"' in self.html),
            "Container para lista de projetos deve existir na sidebar"
        )
        # Botão de exibir mais
        self.assertIn('id="btn-show-more-projects"', self.html, "Botão de Exibir Mais projetos deve existir no HTML")

    def test_js_has_pin_unpin_persistence_and_show_more(self):
        """
        Requisitos 2, 3 e 4: app.js deve conter lógica para:
        - Fixar (pin) e Desafixar (unpin)
        - Persistência em localStorage (cockpit_pinned_projects)
        - Alternância de 'Exibir Mais' (show more / show less)
        - Limite inicial de 3 projetos recentes
        """
        self.assertIn('cockpit_pinned_projects', self.js, "app.js deve salvar projetos fixados em localStorage")
        self.assertIn('togglePinProject', self.js, "app.js deve ter função para alternar fixação de projeto")
        self.assertIn('btn-show-more-projects', self.js, "app.js deve controlar o botão de exibir mais projetos")

    def test_css_has_pin_button_and_show_more_styling(self):
        """
        Estilização clean para botões de fixar/desafixar e botão Exibir Mais.
        """
        self.assertIn('.btn-pin-action', self.css, "Estilo para botão de pin/unpin deve existir no CSS")
        self.assertIn('.btn-show-more-projects', self.css, "Estilo para botão Exibir Mais deve existir no CSS")


if __name__ == '__main__':
    unittest.main()
