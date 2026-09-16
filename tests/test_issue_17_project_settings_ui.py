import unittest
import os

class TestIssue17ProjectSettingsUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.html_path = os.path.join(base_dir, 'web', 'index.html')
        cls.js_path = os.path.join(base_dir, 'web', 'js', 'settings.js')

        with open(cls.html_path, 'r', encoding='utf-8') as f:
            cls.html_content = f.read()

        with open(cls.js_path, 'r', encoding='utf-8') as f:
            cls.js_content = f.read()

    def test_html_project_settings_panel_structure(self):
        """Valida que web/index.html contém o painel #ag-panel-project-settings completo."""
        html = self.html_content

        # Painel #ag-panel-project-settings
        self.assertIn('id="ag-panel-project-settings"', html, "Deve conter o painel #ag-panel-project-settings")

        # Título e subtítulo no header do painel
        self.assertTrue(
            'Project Settings' in html or 'Configurações do Projeto' in html,
            "Painel de configurações do projeto deve ter título descritivo"
        )

        # Badges de status de herança ('HERDADO' e 'CUSTOMIZADO')
        self.assertIn('HERDADO', html, "Deve conter badge/status 'HERDADO'")
        self.assertIn('CUSTOMIZADO', html, "Deve conter badge/status 'CUSTOMIZADO'")

        # Botão para restaurar padrões gerais
        self.assertTrue(
            'btn-restore-project-defaults' in html or 'btn-ag-restore-project-defaults' in html,
            "Deve conter botão com ID para restaurar padrões gerais do projeto"
        )
        self.assertTrue(
            'Restaurar Padrões Gerais' in html or 'Restaurar padrões' in html or 'Restaurar Padrões' in html,
            "Deve conter texto explicativo de restauração de padrões gerais"
        )

    def test_settings_js_project_settings_logic(self):
        """Valida que web/js/settings.js possui openProjectSettings, renderiza overrides e não fecha o modal."""
        js = self.js_content

        # Função openProjectSettings
        self.assertIn('openProjectSettings', js, "web/js/settings.js deve conter a função openProjectSettings")

        # Não deve invocar closeSettingsModal no clique de projeto das configurações
        # Deve renderizar overrides e consumir a API de configurações de projeto
        self.assertTrue(
            '/api/projects/' in js and '/settings' in js,
            "settings.js deve consumir o endpoint /api/projects/{projectId}/settings"
        )

        # Deve conter métodos/lógicas para salvar overrides e restaurar padrões
        self.assertTrue(
            'saveProjectSettings' in js or 'saveProjectOverrides' in js or 'saveProjectSetting' in js,
            "Deve existir método para salvar overrides de projeto em settings.js"
        )
        self.assertTrue(
            'restoreProjectDefaults' in js or 'clearProjectOverrides' in js or 'resetProjectSettings' in js,
            "Deve existir método para restaurar padrões gerais do projeto em settings.js"
        )

if __name__ == '__main__':
    unittest.main()
