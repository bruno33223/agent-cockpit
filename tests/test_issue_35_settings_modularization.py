import os
import sys
import glob
import unittest
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

SETTINGS_DIR = os.path.join(BASE_DIR, "web", "js", "settings")
SETTINGS_JS_PATH = os.path.join(BASE_DIR, "web", "js", "settings.js")
INDEX_HTML_PATH = os.path.join(BASE_DIR, "web", "index.html")

CORE_MODULES = {
    "omniroute_controller.js": os.path.join(SETTINGS_DIR, "omniroute_controller.js"),
    "appearance_controller.js": os.path.join(SETTINGS_DIR, "appearance_controller.js"),
    "local_ai_controller.js": os.path.join(SETTINGS_DIR, "local_ai_controller.js"),
    "governance_controller.js": os.path.join(SETTINGS_DIR, "governance_controller.js"),
    "settings_main.js": os.path.join(SETTINGS_DIR, "settings_main.js"),
}

MAX_MODULE_LINES = 350
MAX_FACADE_LINES = 150


class TestIssue35SettingsModularization(unittest.TestCase):
    """Testes TDD para a Issue #35 - Decomposição Modular do settings.js."""

    def test_01_modules_exist_and_exports(self):
        """Critério 1: Novos módulos em web/js/settings/ e a fachada web/js/settings.js devem existir e exportar símbolos chave."""
        self.assertTrue(os.path.isdir(SETTINGS_DIR), f"Diretório {SETTINGS_DIR} deve existir.")
        self.assertTrue(os.path.isfile(SETTINGS_JS_PATH), f"Arquivo {SETTINGS_JS_PATH} deve existir.")

        for name, path in CORE_MODULES.items():
            self.assertTrue(os.path.isfile(path), f"Módulo obrigatório não existe: {name} em {path}")

        # Appearance controller
        with open(CORE_MODULES["appearance_controller.js"], "r", encoding="utf-8") as f:
            app_content = f.read()
        self.assertIn("initThemeAndFontSettings", app_content, "appearance_controller.js deve exportar initThemeAndFontSettings")

        # Local AI controller
        with open(CORE_MODULES["local_ai_controller.js"], "r", encoding="utf-8") as f:
            local_content = f.read()
        self.assertIn("loadSettings", local_content, "local_ai_controller.js deve exportar loadSettings")
        self.assertIn("saveSettingUpdate", local_content, "local_ai_controller.js deve exportar saveSettingUpdate")

        # Governance controller
        with open(CORE_MODULES["governance_controller.js"], "r", encoding="utf-8") as f:
            gov_content = f.read()
        self.assertIn("loadGovernanceSettings", gov_content, "governance_controller.js deve exportar loadGovernanceSettings")
        self.assertIn("openProjectSettings", gov_content, "governance_controller.js deve exportar openProjectSettings")
        self.assertIn("saveProjectSettings", gov_content, "governance_controller.js deve exportar saveProjectSettings")

        # OmniRoute controller
        with open(CORE_MODULES["omniroute_controller.js"], "r", encoding="utf-8") as f:
            omni_content = f.read()
        self.assertIn("openOmniRouteAccountModal", omni_content, "omniroute_controller.js deve exportar openOmniRouteAccountModal")
        self.assertIn("closeOmniRouteAccountModal", omni_content, "omniroute_controller.js deve exportar closeOmniRouteAccountModal")
        self.assertIn("saveOmniRouteAccount", omni_content, "omniroute_controller.js deve exportar saveOmniRouteAccount")

        # Settings Main
        with open(CORE_MODULES["settings_main.js"], "r", encoding="utf-8") as f:
            main_content = f.read()
        self.assertTrue(
            "SettingsModal" in main_content or "initSettingsMain" in main_content or "initAllSettings" in main_content,
            "settings_main.js deve conter a inicialização central do modal de configurações"
        )

    def test_02_sloc_limits(self):
        """Critério 2: Nenhum arquivo em web/js/settings/*.js deve passar de 350 linhas e settings.js <= 150 linhas."""
        # Verifica a fachada settings.js
        with open(SETTINGS_JS_PATH, "r", encoding="utf-8") as f:
            facade_lines = f.readlines()
        self.assertLessEqual(
            len(facade_lines),
            MAX_FACADE_LINES,
            f"web/js/settings.js possui {len(facade_lines)} linhas, excedendo o limite estrito de {MAX_FACADE_LINES} linhas!"
        )

        # Verifica todos os arquivos em web/js/settings/*.js
        settings_files = glob.glob(os.path.join(SETTINGS_DIR, "*.js"))
        self.assertGreater(len(settings_files), 0, "Nenhum arquivo JS encontrado em web/js/settings/")

        for file_path in settings_files:
            file_name = os.path.basename(file_path)
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            line_count = len(lines)
            self.assertLessEqual(
                line_count,
                MAX_MODULE_LINES,
                f"Arquivo {file_name} possui {line_count} linhas, excedendo o limite estrito de {MAX_MODULE_LINES} linhas!"
            )

    def test_03_index_html_script_order(self):
        """Critério 3: web/index.html deve incluir os novos scripts na ordem correta antes de app.js."""
        self.assertTrue(os.path.isfile(INDEX_HTML_PATH), "web/index.html deve existir")
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            html = f.read()

        for mod_name in CORE_MODULES.keys():
            self.assertIn(mod_name, html, f"index.html deve referenciar {mod_name}")

        idx_app = html.find("app.js")
        self.assertNotEqual(idx_app, -1, "index.html deve referenciar app.js")

        for mod_name in CORE_MODULES.keys():
            idx_mod = html.find(mod_name)
            self.assertLess(
                idx_mod,
                idx_app,
                f"Módulo {mod_name} deve ser carregado antes de app.js em web/index.html"
            )

    def test_04_separation_of_responsibilities(self):
        """Critério 4: Validação de SOLID e separação de responsabilidades entre os módulos."""
        # appearance_controller.js: temas, variáveis de cor, fontes
        with open(CORE_MODULES["appearance_controller.js"], "r", encoding="utf-8") as f:
            app_js = f.read()
        self.assertIn("ag_theme", app_js)
        self.assertIn("ag_font_scale", app_js)

        # local_ai_controller.js: Ollama, hardware preferences, workers
        with open(CORE_MODULES["local_ai_controller.js"], "r", encoding="utf-8") as f:
            local_js = f.read()
        self.assertIn("/api/settings", local_js)

        # governance_controller.js: human gates, autostart, project overrides
        with open(CORE_MODULES["governance_controller.js"], "r", encoding="utf-8") as f:
            gov_js = f.read()
        self.assertIn("/api/governance", gov_js)
        self.assertIn("/api/projects/", gov_js)

        # omniroute_controller.js: rotas omniroute, contas, modelos
        with open(CORE_MODULES["omniroute_controller.js"], "r", encoding="utf-8") as f:
            omni_js = f.read()
        self.assertIn("/api/omniroute", omni_js)

        # settings_main.js: coordenação de abas e modal
        with open(CORE_MODULES["settings_main.js"], "r", encoding="utf-8") as f:
            main_js = f.read()
        self.assertIn("ag-nav-item", main_js)

    def test_05_syntax_check_node(self):
        """Critério 5: Validação de sintaxe JS via Node.js em todos os arquivos modificados e criados."""
        all_files = [SETTINGS_JS_PATH] + glob.glob(os.path.join(SETTINGS_DIR, "*.js"))
        for file_path in all_files:
            if os.path.exists(file_path):
                res = subprocess.run(["node", "--check", file_path], capture_output=True, text=True)
                self.assertEqual(res.returncode, 0, f"Erro de sintaxe em {file_path}: {res.stderr}")

    def test_06_retrocompatibility_facade_exports(self):
        """Critério 6: web/js/settings.js deve preservar exports legados e window.SettingsModal."""
        with open(SETTINGS_JS_PATH, "r", encoding="utf-8") as f:
            js = f.read()

        required_exports = [
            "openOmniRouteAccountModal",
            "closeOmniRouteAccountModal",
            "saveOmniRouteAccount",
            "selectOmniRouteProviderPill",
            "loadOmniRouteConnectors",
            "renderOmniRouteConnectors",
            "autofillOpenCodeCredentials",
            "checkAutostartStatus",
            "setSystemAutostart",
            "updateHumanGateUI",
            "approveHumanGate",
            "loadSettings",
            "applySettingsToUI",
            "saveSettingUpdate",
            "initThemeAndFontSettings",
            "loadCustomizations",
            "openProjectSettings",
            "saveProjectSettings",
            "restoreProjectDefaults",
            "SettingsModal"
        ]
        for item in required_exports:
            self.assertIn(item, js, f"settings.js fachada deve exportar ou referenciar '{item}' para retrocompatibilidade")


if __name__ == "__main__":
    unittest.main()
