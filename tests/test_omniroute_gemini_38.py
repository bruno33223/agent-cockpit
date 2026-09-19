import unittest
from unittest.mock import patch, MagicMock
import json

from server import opencode_manager
from server import zeus_chat_engine

class TestOmnirouteGemini38(unittest.TestCase):
    """Testes para suporte e descoberta do modelo Gemini 3.8 Flash no OmniRoute e Zeus Chat."""

    def test_vision_model_supports_gemini_38(self):
        """Verifica se is_vision_model reconhece modelos gemini 3.8."""
        self.assertTrue(zeus_chat_engine.is_vision_model("gemini-3.8-flash"))
        self.assertTrue(zeus_chat_engine.is_vision_model("gemini-3.8-flash-high"))
        self.assertTrue(zeus_chat_engine.is_vision_model("gemini-3.8-flash-medium"))
        self.assertTrue(zeus_chat_engine.is_vision_model("gemini-3.8-flash-low"))
        self.assertTrue(zeus_chat_engine.is_vision_model("gemini-3.8-flash-tiered"))
        self.assertTrue(zeus_chat_engine.is_vision_model("antigravity/gemini-3.8-flash-tiered"))
        self.assertTrue(zeus_chat_engine.is_vision_model("omniroute/antigravity/gemini-3.8-flash"))

    def test_detect_omniroute_connectors_includes_gemini_38(self):
        """Verifica se detect_omniroute_connectors inclui gemini-3.8 nas opções do conector antigravity."""
        mock_models_response = {
            "data": [
                {"id": "antigravity/gemini-3.7-flash-high"},
                {"id": "antigravity/gemini-3.8-flash-tiered"},
                {"id": "antigravity/gemini-3.8-flash"},
                {"id": "openai/gpt-4o"}
            ]
        }
        
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_models_response).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp
            
            connectors = opencode_manager.detect_omniroute_connectors("http://127.0.0.1:20128/v1")
            
            ag_connector = next((c for c in connectors if c["id"] == "antigravity"), None)
            self.assertIsNotNone(ag_connector)
            self.assertIn("antigravity/gemini-3.8-flash-tiered", ag_connector["models"])
            self.assertIn("antigravity/gemini-3.8-flash", ag_connector["models"])

    def test_list_omniroute_live_models_merges_provider_account_models(self):
        """Verifica se list_omniroute_live_models agrega modelos vivos de /api/v1/providers/antigravity/models se faltarem em /v1/models."""
        # /v1/models só retorna 3.7
        v1_models_response = {
            "data": [
                {"id": "antigravity/gemini-3.7-flash-high"},
                {"id": "openai/gpt-4o"}
            ]
        }
        # /api/v1/providers/antigravity/models retorna 3.8
        ag_provider_response = {
            "object": "list",
            "data": [
                {"id": "gemini-3.8-flash-tiered", "name": "gemini-3.8-flash-tiered"}
            ]
        }
        
        def fake_urlopen(req, *args, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            resp = MagicMock()
            resp.__enter__.return_value = resp
            if "/api/v1/providers/antigravity/models" in url:
                resp.read.return_value = json.dumps(ag_provider_response).encode("utf-8")
            elif "/v1/models" in url:
                resp.read.return_value = json.dumps(v1_models_response).encode("utf-8")
            else:
                resp.read.return_value = b"{}"
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = opencode_manager.list_omniroute_live_models("http://127.0.0.1:20128")
            self.assertEqual(res["status"], "ok")
            models = res["models"]
            # Deve incluir tanto 3.7 quanto 3.8
            self.assertIn("antigravity/gemini-3.7-flash-high", models)
            self.assertIn("antigravity/gemini-3.8-flash-tiered", models)

    def test_zeus_engine_model_sanitization_gemini_38(self):
        """Verifica se zeus_engine limpa o model_id para gemini 3.8 sem prefixos omniroute."""
        engine = zeus_chat_engine.ZeusChatEngine()
        
        with patch.object(engine, "_stream_omniroute") as mock_stream:
            mock_stream.return_value = iter([{"type": "content", "text": "Teste OK"}])
            
            events = list(engine.stream_chat(
                session_id="test-session",
                message="Ola",
                model_id="omniroute/antigravity/gemini-3.8-flash"
            ))
            
            self.assertTrue(len(events) > 0)
            mock_stream.assert_called_once()
            called_model = mock_stream.call_args[1].get("model_id") or mock_stream.call_args[0][2]
            # O model_id repassado deve ser antigravity/gemini-3.8-flash
            self.assertEqual(called_model, "antigravity/gemini-3.8-flash")

if __name__ == "__main__":
    unittest.main()
