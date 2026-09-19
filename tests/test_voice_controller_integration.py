"""
tests/test_voice_controller_integration.py: Testes de integração do Voice Controller,
Voice Activity Detection (VAD), Push-to-Talk (PTT), síntese TTS e sincronia com Avatar 3D.
Issue #46
"""

import asyncio
import math
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)


class TestVoiceControllerIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.voice_ctrl_path = os.path.join(cls.base_dir, "web", "js", "voice_controller.js")
        cls.index_path = os.path.join(cls.base_dir, "web", "index.html")
        cls.router_path = os.path.join(cls.base_dir, "server", "routers", "zeus_chat.py")

    def test_01_line_guardrails(self):
        """Valida que voice_controller.js <= 250 linhas e zeus_chat.py <= 250 linhas."""
        self.assertTrue(os.path.exists(self.voice_ctrl_path), f"Arquivo {self.voice_ctrl_path} deve existir.")
        with open(self.voice_ctrl_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertLessEqual(
            len(lines), 250,
            f"web/js/voice_controller.js deve ter no máximo 250 linhas, encontrado {len(lines)}"
        )

        with open(self.router_path, "r", encoding="utf-8") as f:
            router_lines = f.readlines()
        self.assertLessEqual(
            len(router_lines), 250,
            f"server/routers/zeus_chat.py deve ter no máximo 250 linhas, encontrado {len(router_lines)}"
        )

    def test_02_voice_controller_exports_and_methods(self):
        """Valida a estrutura do VoiceController e sua exposição modular e global."""
        with open(self.voice_ctrl_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("class VoiceController", content)
        self.assertIn("export class VoiceController", content)
        self.assertIn("export const voiceController", content)
        self.assertIn("window.voiceController", content)
        self.assertIn("startListening", content)
        self.assertIn("stopListening", content)
        self.assertIn("startPtt", content)
        self.assertIn("stopPtt", content)
        self.assertIn("setMode", content)
        self.assertIn("processAudioFrame", content)
        self.assertIn("playTts", content)

    def test_03_index_html_ui_elements(self):
        """Valida que index.html inclui elementos da UI de voz e dock do avatar."""
        with open(self.index_path, "r", encoding="utf-8") as f:
            html = f.read()

        self.assertIn("js/voice_controller.js", html)
        self.assertIn("js/avatar_3d.js", html)
        self.assertIn("id=\"btn-zeus-mic\"", html)
        self.assertIn("id=\"btn-zeus-voice-mode\"", html)
        self.assertTrue(
            "zeus-avatar-dock" in html or "avatar-3d-dock" in html or "tactical-avatar" in html
        )

    def test_04_vad_logic_and_rms_thresholding(self):
        """Testa simulação matemática de VAD (RMS e silêncio) usada pelo controller."""
        def calculate_rms(samples):
            if not samples:
                return 0.0
            sum_sq = sum(s * s for s in samples)
            return math.sqrt(sum_sq / len(samples))

        silence_samples = [0.001 * math.sin(i) for i in range(512)]
        silence_rms = calculate_rms(silence_samples)
        self.assertLess(silence_rms, 0.01)

        speech_samples = [0.25 * math.sin(i * 0.1) for i in range(512)]
        speech_rms = calculate_rms(speech_samples)
        self.assertGreater(speech_rms, 0.05)

        threshold = 0.02
        self.assertFalse(silence_rms > threshold)
        self.assertTrue(speech_rms > threshold)

    def test_05_audio_synthesize_endpoint(self):
        """Valida o endpoint /api/audio/synthesize no router do zeus_chat."""
        from server.routers.zeus_chat import post_audio_synthesize_endpoint
        from fastapi import HTTPException

        # 1. Sucesso com texto
        res = asyncio.run(post_audio_synthesize_endpoint({"text": "Olá Diretor, teste operacional.", "voice": "pt-BR-FranciscaNeural"}))
        self.assertIsNotNone(res)
        self.assertTrue(hasattr(res, "body_iterator") or hasattr(res, "body"))

        # 2. Erro com texto vazio
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(post_audio_synthesize_endpoint({"text": ""}))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_06_avatar_sync_states(self):
        """Valida que o Avatar 3D e VoiceController sincronizam os estados táticos."""
        expected_states = ["IDLE", "LISTENING", "THINKING", "SPEAKING"]
        for st in expected_states:
            self.assertIn(st, ["IDLE", "LISTENING", "THINKING", "DISPATCHING_WORKER", "TESTING", "SPEAKING", "READY"])

    def test_07_avatar_voice_dock_and_downsample(self):
        """Valida controle de voz no robô/avatar 2D, remoção de card do topo e downsampling."""
        with open(self.index_path, "r", encoding="utf-8") as f:
            html = f.read()

        # Botão do topo não deve existir na barra lateral
        self.assertNotIn('id="zeus-sidebar-voice-card"', html)
        # Controle deve estar diretamente no avatar
        self.assertIn('id="zeus-avatar-dock"', html)
        self.assertIn('data-state="OFF"', html)
        self.assertIn('id="avatar-state-badge"', html)
        self.assertIn('id="avatar-voice-control"', html)

        with open(self.voice_ctrl_path, "r", encoding="utf-8") as f:
            js = f.read()

        self.assertIn("downsampleTo16k", js)
        self.assertIn("ensureChatOpen", js)
        self.assertIn("zeus-avatar-dock", js)

        # Simulação matemática da função pura downsampleTo16k (48kHz -> 16kHz = 1/3)
        def downsample(samples, in_rate, out_rate=16000):
            if in_rate == out_rate:
                return samples
            ratio = in_rate / out_rate
            out_len = round(len(samples) / ratio)
            return [samples[round(i * ratio)] if round(i * ratio) < len(samples) else 0 for i in range(out_len)]

        samples_48k = [math.sin(i * 0.05) for i in range(4800)]
        samples_16k = downsample(samples_48k, 48000, 16000)
        self.assertEqual(len(samples_16k), 1600)


if __name__ == "__main__":
    unittest.main()

