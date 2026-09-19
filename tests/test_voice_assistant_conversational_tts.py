"""
tests/test_voice_assistant_conversational_tts.py: Validação de intenção conversacional,
eliminação de mock de áudio e síntese de voz TTS com fallback nativo.
"""

import os
import unittest
from unittest.mock import patch, MagicMock

from server.chat.prompt_optimizer import PromptOptimizer
from server.chat.audio_transcriber import AudioTranscriber


class TestConversationalIntentOptimization(unittest.TestCase):
    """Garante que perguntas e conversações com Zeus não sejam distorcidas em ordens técnicas."""

    def setUp(self):
        self.optimizer = PromptOptimizer()

    def test_conversational_inquiries_preserve_natural_question(self):
        """Perguntas sobre integridade e status não devem receber prefixo imperativo de tarefa."""
        q1 = "como está a integridade do sistema"
        res1 = self.optimizer.optimize(q1)
        self.assertFalse(res1.startswith("[Executar tarefa técnica]:"))
        self.assertFalse(res1.startswith("[Executar e validar testes]:"))
        self.assertIn("integridade do sistema", res1.lower())
        self.assertTrue(res1.endswith("?"))

        q2 = "qual o status do projeto e dos subagentes?"
        res2 = self.optimizer.optimize(q2)
        self.assertFalse(res2.startswith("["))
        self.assertIn("status do projeto", res2.lower())

        q3 = "olá zeus tudo bem com você?"
        res3 = self.optimizer.optimize(q3)
        self.assertFalse(res3.startswith("["))
        self.assertTrue(res3.startswith("Olá"))

    def test_imperative_technical_commands_still_receive_intent_labels(self):
        """Comandos imperativos claros continuam sendo estruturados pelo PromptOptimizer."""
        cmd1 = "conserta o bug no endpoint de auth"
        res1 = self.optimizer.optimize(cmd1)
        self.assertTrue(res1.startswith("[Corrigir defeito]:"))

        cmd2 = "implemente uma nova rota para exportar relatório"
        res2 = self.optimizer.optimize(cmd2)
        self.assertTrue(res2.startswith("[Implementar funcionalidade]:"))

        cmd3 = "roda os testes e valida a suíte completa"
        res3 = self.optimizer.optimize(cmd3)
        self.assertTrue(res3.startswith("[Executar e validar testes]:"))


class TestAudioTranscriberEliminatesMock(unittest.TestCase):
    """Garante que áudio não reconhecido não injete falsas instruções de integridade/testes."""

    def setUp(self):
        self.transcriber = AudioTranscriber()

    def test_no_hardcoded_integrity_test_string(self):
        """Bytes aleatórios de áudio nunca devem retornar instrução forjada de teste de integridade."""
        random_audio = b"\x00\x05" * 600  # 1200 bytes
        res = self.transcriber._acoustic_heuristic_transcription(random_audio)
        self.assertNotIn("verificação de integridade e testes", res.lower())
        self.assertNotIn("executar verificação", res.lower())


class TestVoiceAndTtsArchitectureGuardrails(unittest.TestCase):
    """Valida o código fonte do frontend e os limites rígidos de linhas (KISS <= 250)."""

    def setUp(self):
        self.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    def test_source_files_under_250_lines(self):
        """Nenhum módulo de chat ou voz pode ultrapassar 250 linhas."""
        files = [
            os.path.join(self.root_dir, "web", "js", "voice_controller.js"),
            os.path.join(self.root_dir, "web", "js", "zeus_chat_workspace.js"),
            os.path.join(self.root_dir, "server", "chat", "audio_transcriber.py"),
            os.path.join(self.root_dir, "server", "chat", "prompt_optimizer.py"),
        ]
        for fpath in files:
            with open(fpath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            self.assertLessEqual(
                len(lines), 250,
                f"{os.path.basename(fpath)} tem {len(lines)} linhas; limite é <= 250."
            )

    def test_voice_controller_has_tts_resilience_and_speech_synthesis_fallback(self):
        """voice_controller.js deve ter suporte a SpeechSynthesis como fallback resiliente."""
        fpath = os.path.join(self.root_dir, "web", "js", "voice_controller.js")
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("speechSynthesis", content, "voice_controller.js deve implementar fallback para window.speechSynthesis")
        self.assertIn("SpeechSynthesisUtterance", content, "voice_controller.js deve instanciar SpeechSynthesisUtterance")


if __name__ == "__main__":
    unittest.main()
