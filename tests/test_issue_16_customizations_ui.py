import unittest
import os

class TestIssue16CustomizationsUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html_path = os.path.join(base_dir, 'web', 'index.html')
        cls.js_path = os.path.join(base_dir, 'web', 'js', 'settings.js')

        with open(cls.html_path, 'r', encoding='utf-8') as f:
            cls.html_content = f.read()

        with open(cls.js_path, 'r', encoding='utf-8') as f:
            cls.js_content = f.read()

    def test_html_dynamic_containers_and_modals(self):
        """Valida que web/index.html substituiu lista hardcoded por containers dinâmicos e modais."""
        html = self.html_content

        # Containers dinâmicos
        self.assertIn('id="mcp-servers-list"', html, "Deve existir o container dinâmico #mcp-servers-list")
        self.assertIn('id="skills-list"', html, "Deve existir o container dinâmico #skills-list")

        # Ausência da lista estática hardcoded antiga no painel de customizations
        self.assertNotIn('26 Tools registradas (Stdio)', html, "Lista estática hardcoded antiga deve ser removida")
        self.assertNotIn('10 Tools de fluxos e documentação', html, "Lista estática antiga deve ser removida")

        # Botões de adicionar
        self.assertTrue('id="btn-add-mcp"' in html or 'id="btn-ag-add-mcp"' in html, "Deve existir botão para adicionar Servidor MCP")
        self.assertTrue('id="btn-add-skill"' in html or 'id="btn-ag-add-skill"' in html, "Deve existir botão para adicionar Skill")

        # Modais / formulários de criação e edição
        self.assertTrue('id="modal-mcp-form"' in html or 'id="modal-mcp-server"' in html or 'id="modal-mcp-editor"' in html, "Deve existir modal de configuração/edição de MCP")
        self.assertTrue('id="modal-skill-form"' in html or 'id="modal-skill-editor"' in html or 'id="modal-skill"' in html, "Deve existir modal de configuração/edição de Skill")

    def test_settings_js_customizations_methods(self):
        """Valida que web/js/settings.js contém os métodos de consumo da API e bindings de eventos."""
        js = self.js_content

        # Métodos obrigatórios
        required_methods = [
            'loadCustomizations',
            'renderMcpList',
            'renderSkillsList',
            'toggleMcpServer',
            'deleteMcpServer',
            'saveMcpServer',
            'saveSkill'
        ]
        for method in required_methods:
            self.assertIn(method, js, f"Método '{method}' deve existir em web/js/settings.js")

        # Endpoints de API consumidos
        self.assertIn('/api/customizations/mcp', js, "settings.js deve chamar /api/customizations/mcp")
        self.assertIn('/api/customizations/skills', js, "settings.js deve chamar /api/customizations/skills")

        # Bindings e inicialização
        self.assertTrue(
            'initCustomizationsEvents' in js or 'initCustomizations' in js,
            "Deve existir função de inicialização/bindings de eventos para customizations"
        )

if __name__ == '__main__':
    unittest.main()
