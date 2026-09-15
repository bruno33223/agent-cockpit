import os
import unittest
import re

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR = os.path.join(BASE_DIR, "web")

class TestIssue1UICleanup(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(WEB_DIR, "index.html"), "r", encoding="utf-8") as f:
            self.html = f.read()
        with open(os.path.join(WEB_DIR, "styles.css"), "r", encoding="utf-8") as f:
            self.css = f.read()
        with open(os.path.join(WEB_DIR, "app.js"), "r", encoding="utf-8") as f:
            self.js = f.read()

    def test_mac_traffic_lights_removed_from_html(self):
        """1. Remover Controles Mac: Eliminar o semáforo macOS (.mac-traffic-lights)."""
        self.assertNotIn('class="mac-traffic-lights"', self.html)
        self.assertNotIn('class="mac-dot', self.html)

    def test_redundant_nav_buttons_removed_from_html(self):
        """2 & 3. Titlebar Limpa: apenas Título e Search (Ctrl+K); sem Tasks, Automations, Orca Mobile."""
        self.assertNotIn('id="nav-quick-tasks"', self.html)
        self.assertNotIn('id="nav-quick-automations"', self.html)
        self.assertNotIn('id="nav-quick-mobile"', self.html)
        # Search e Brand devem permanecer
        self.assertIn('id="nav-quick-search"', self.html)
        self.assertIn('orca-brand', self.html)

    def test_orca_mobile_modal_removed_from_html_and_js(self):
        """4. Remover Modal Orca Mobile: Descartar #orca-mobile-modal e seus hooks."""
        self.assertNotIn('id="orca-mobile-modal"', self.html)
        self.assertNotIn('id="btn-close-mobile-modal"', self.html)
        self.assertNotIn('id="btn-mobile-sync-now"', self.html)
        self.assertNotIn('openOrcaMobileModal', self.js)
        self.assertNotIn('closeOrcaMobileModal', self.js)

    def test_usage_meter_removed_from_html(self):
        """5. Remover Medidor de Usage: Excluir a barra de cota/usage do rodapé da sidebar."""
        self.assertNotIn('class="sidebar-usage-meter"', self.html)
        self.assertNotIn('class="usage-meter-header"', self.html)

    def test_ws_status_pill_removed_from_titlebar_html(self):
        """6. Remover Indicador 'WS Online': Não deve poluir a titlebar."""
        # Não deve haver conn-pill ou ws-status na titlebar
        titlebar_match = re.search(r'<header[^>]*class="[^"]*titlebar[^"]*"[^>]*>(.*?)</header>', self.html, re.DOTALL)
        self.assertTrue(titlebar_match, "Titlebar deve existir")
        titlebar_content = titlebar_match.group(1)
        self.assertNotIn('id="ws-status"', titlebar_content)
        self.assertNotIn('id="ws-status-text"', titlebar_content)

    def test_buttons_minimalist_and_compact_in_css(self):
        """7. Botões Menores e Mais Minimalistas: altura 28-32px, border-radius 4-6px."""
        # Validação do .action-btn
        action_btn_match = re.search(r'\.action-btn\s*\{([^}]+)\}', self.css)
        self.assertTrue(action_btn_match, ".action-btn deve estar definido em styles.css")
        action_btn_body = action_btn_match.group(1)

        # Border-radius entre 4px e 6px
        br_match = re.search(r'border-radius:\s*([0-9]+)px', action_btn_body)
        self.assertTrue(br_match, "border-radius deve estar definido em px para .action-btn")
        radius = int(br_match.group(1))
        self.assertTrue(4 <= radius <= 6, f"border-radius de .action-btn ({radius}px) deve estar entre 4px e 6px")

        # Altura entre 28px e 32px
        h_match = re.search(r'height:\s*([0-9]+)px', action_btn_body)
        self.assertTrue(h_match, "height deve estar definido em px para .action-btn")
        height = int(h_match.group(1))
        self.assertTrue(28 <= height <= 32, f"height de .action-btn ({height}px) deve estar entre 28px e 32px")

        # action-btn primary definido
        self.assertIn('.action-btn.primary', self.css)

if __name__ == "__main__":
    unittest.main()
