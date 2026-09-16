import os
import re
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR = os.path.join(BASE_DIR, "web")
JS_DIR = os.path.join(WEB_DIR, "js")
SIDEBAR_JS_PATH = os.path.join(JS_DIR, "sidebar.js")
SETTINGS_JS_PATH = os.path.join(JS_DIR, "settings.js")
SLICES_CHAT_JS_PATH = os.path.join(JS_DIR, "slices_chat.js")


class TestIssue23SinglePostAndWSPolling(unittest.TestCase):
    """
    Testes para a Issue #23:
    - Eliminar duplo POST de OmniRoute (sem click simulado cruzado).
    - Salvar OmniRoute exclusivamente com apiFetch em settings.js.
    - Remover polling incondicional a cada 2s no slices_chat.js, condicionando à ausência de WebSocket.
    """

    def setUp(self):
        with open(SIDEBAR_JS_PATH, "r", encoding="utf-8") as f:
            self.sidebar_js = f.read()
        with open(SETTINGS_JS_PATH, "r", encoding="utf-8") as f:
            self.settings_js = f.read()
        with open(SLICES_CHAT_JS_PATH, "r", encoding="utf-8") as f:
            self.slices_chat_js = f.read()

    def test_sidebar_no_simulated_click_on_legacy_save(self):
        """
        Garante que sidebar.js não dispara cliques artificiais (.click())
        em btn-save-omniroute-config ou elementos legados para salvar omniroute.
        """
        # Não deve haver chamada .click() em origSave ou btn-save-omniroute-config
        self.assertNotIn(
            "origSave.click()",
            self.sidebar_js,
            "sidebar.js não deve chamar origSave.click() para evitar duplo POST."
        )
        self.assertNotRegex(
            self.sidebar_js,
            r"btn-save-omniroute-config['\"]?\)\s*\.\s*click\(",
            "sidebar.js não deve forçar click() no formulário legado de omniroute."
        )

    def test_settings_uses_apifetch_for_omniroute_config(self):
        """
        Garante que salvar omniroute seja feito exclusivamente com apiFetch
        em settings.js (e não com fetch nativo desacoplado).
        """
        # settings.js deve usar apiFetch('/api/omniroute/config'
        self.assertIn(
            "apiFetch('/api/omniroute/config'",
            self.settings_js,
            "settings.js deve utilizar apiFetch para salvar /api/omniroute/config com headers padronizados."
        )
        # Não deve haver fetch('/api/omniroute/config' com method POST
        self.assertNotRegex(
            self.settings_js,
            r"fetch\(['\"]/api/omniroute/config['\"],\s*\{\s*method:\s*['\"]POST['\"]",
            "settings.js não deve usar fetch cru para POST /api/omniroute/config; deve usar apiFetch."
        )

    def test_slices_chat_no_unconditional_2s_polling(self):
        """
        Garante que slices_chat.js não execute polling incondicional a cada 2s;
        o polling deve ser condicionado à ausência de WebSocket ativo (WebSocket.OPEN).
        """
        # Não deve haver polling cego incondicional
        unconditional_polling = re.search(
            r"setInterval\s*\(\s*async\s*\(\)\s*=>\s*\{\s*try\s*\{\s*const\s+res\s*=\s*await\s+apiFetch\([^)]+\);\s*if\s*\(res\.ok\)",
            self.slices_chat_js
        )
        self.assertIsNone(
            unconditional_polling,
            "slices_chat.js não deve possuir setInterval cego incondicional para buscar /api/state a cada 2s."
        )

        # Deve verificar status do WebSocket antes do polling de fallback
        self.assertRegex(
            self.slices_chat_js,
            r"(WebSocket\.OPEN|isWsActive|isWebSocketActive|isWebSocketConnected)",
            "slices_chat.js deve verificar se o WebSocket está conectado antes de executar polling de fallback."
        )


if __name__ == "__main__":
    unittest.main()
