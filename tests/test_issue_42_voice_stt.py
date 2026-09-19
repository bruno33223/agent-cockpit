"""
tests/test_issue_42_voice_stt.py: Validação de Voice & STT, decodificação resiliente e limites de linhas.
Issue #42: [Voice & STT] Modelo local de IA para transcrição de áudio e correção do pipeline de microfone
"""

import io
import math
import os
import struct
import unittest
from unittest.mock import patch, MagicMock


def generate_wav_bytes(duration_sec=0.5, sample_rate=16000, freq=440.0, volume=0.5) -> bytes:
    """Gera bytes de um arquivo WAV válido com onda senoidal de 16-bit mono."""
    num_samples = int(duration_sec * sample_rate)
    pcm_data = bytearray()
    for i in range(num_samples):
        val = int(volume * 32767.0 * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
        pcm_data.extend(struct.pack("<h", max(-32768, min(32767, val))))

    wav_header = bytearray()
    wav_header.extend(b"RIFF")
    wav_header.extend(struct.pack("<I", 36 + len(pcm_data)))
    wav_header.extend(b"WAVEfmt ")
    wav_header.extend(struct.pack("<I", 16))
    wav_header.extend(struct.pack("<H", 1))  # PCM
    wav_header.extend(struct.pack("<H", 1))  # Mono
    wav_header.extend(struct.pack("<I", sample_rate))
    wav_header.extend(struct.pack("<I", sample_rate * 2))  # Byte rate
    wav_header.extend(struct.pack("<H", 2))  # Block align
    wav_header.extend(struct.pack("<H", 16))  # Bits per sample
    wav_header.extend(b"data")
    wav_header.extend(struct.pack("<I", len(pcm_data)))

    return bytes(wav_header + pcm_data)


def generate_raw_pcm_bytes(duration_sec=0.5, sample_rate=16000, freq=440.0, volume=0.5) -> bytes:
    """Gera bytes de raw PCM (16-bit little-endian mono) sem cabeçalho RIFF."""
    num_samples = int(duration_sec * sample_rate)
    pcm_data = bytearray()
    for i in range(num_samples):
        val = int(volume * 32767.0 * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
        pcm_data.extend(struct.pack("<h", max(-32768, min(32767, val))))
    return bytes(pcm_data)


class TestIssue42LineLimits(unittest.TestCase):
    """Garante que nenhum arquivo alterado viole o limite rígido de 250 linhas."""

    def test_file_line_limits(self):
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        files_to_check = [
            (os.path.join(root_dir, "web", "js", "chat", "zeus_chat_core.js"), 250),
            (os.path.join(root_dir, "web", "js", "zeus_chat_workspace.js"), 250),
            (os.path.join(root_dir, "server", "chat", "audio_transcriber.py"), 250),
            (os.path.join(root_dir, "tests", "test_issue_42_voice_stt.py"), 400),
        ]
        for path, limit in files_to_check:
            self.assertTrue(os.path.exists(path), f"Arquivo não encontrado: {path}")
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            self.assertLessEqual(
                len(lines),
                limit,
                f"Arquivo {os.path.basename(path)} excedeu limite: {len(lines)} > {limit} linhas."
            )


class TestFrontendMicrophonePipeline(unittest.TestCase):
    """Verifica requisitos do frontend em zeus_chat_core.js e zeus_chat_workspace.js."""

    def setUp(self):
        self.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        core_js_path = os.path.join(self.root_dir, "web", "js", "chat", "zeus_chat_core.js")
        with open(core_js_path, "r", encoding="utf-8") as f:
            self.core_js = f.read()

        workspace_js_path = os.path.join(self.root_dir, "web", "js", "zeus_chat_workspace.js")
        with open(workspace_js_path, "r", encoding="utf-8") as f:
            self.workspace_js = f.read()

    def test_core_has_fallback_from_recognition_error_to_mediadevices(self):
        """Verifica se o erro em SpeechRecognition dispara fallback para gravação de áudio."""
        self.assertIn(
            "mediaDevices.getUserMedia",
            self.core_js,
            "zeus_chat_core.js deve usar navigator.mediaDevices.getUserMedia"
        )
        self.assertTrue(
            "startMediaRecording" in self.core_js or "fallback" in self.core_js or "recordAudio" in self.core_js or "_startMedia" in self.core_js or "mediaRecorder" in self.core_js,
            "zeus_chat_core.js deve ter suporte a gravação de mídia"
        )
        # Deve empacotar WAV ou PCM mono 16kHz
        self.assertTrue(
            "RIFF" in self.core_js or "audio/wav" in self.core_js or "prompt_audio.wav" in self.core_js,
            "zeus_chat_core.js deve enviar áudio no formato WAV (16kHz mono)"
        )

    def test_workspace_handles_microphone_error_callback(self):
        """Verifica se toggleRecording no workspace implementa callback onError."""
        self.assertIn(
            "onError",
            self.workspace_js,
            "zeus_chat_workspace.js deve tratar callback onError no toggleRecording"
        )


class TestAudioTranscriberResilience(unittest.TestCase):
    """Verifica decodificação resiliente de áudio e tolerância a formatos no backend."""

    def setUp(self):
        from server.chat.audio_transcriber import AudioTranscriber
        self.transcriber = AudioTranscriber()

    def test_decode_valid_wav(self):
        """Áudio WAV válido com sinal deve ser processado sem erro."""
        wav_data = generate_wav_bytes(duration_sec=0.4, sample_rate=16000, freq=440.0, volume=0.6)
        result = self.transcriber.transcribe(wav_data)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)
        self.assertNotIn("wave.Error", result)

    def test_decode_raw_pcm_without_riff_header(self):
        """Áudio raw PCM (sem header RIFF) não pode estourar wave.Error e deve ser decodificado."""
        pcm_data = generate_raw_pcm_bytes(duration_sec=0.5, sample_rate=16000, freq=500.0, volume=0.5)
        result = self.transcriber.transcribe(pcm_data)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)
        self.assertNotIn("wave.Error", result)

    def test_inaudible_silence_detection(self):
        """Áudio com silêncio ou volume nulo deve retornar detecção de sinal inaudível."""
        silent_wav = generate_wav_bytes(duration_sec=0.3, sample_rate=16000, freq=0.0, volume=0.0)
        result = self.transcriber.transcribe(silent_wav)
        self.assertIn("silêncio detectado", result.lower())

    def test_empty_audio_bytes(self):
        """Bytes vazios devem retornar mensagem adequada."""
        result = self.transcriber.transcribe(b"")
        self.assertEqual(result, "Nenhum áudio detectado.")


class TestSTTAIRoutingAndNormalization(unittest.TestCase):
    """Verifica integração com OmniRoute (/v1/audio/transcriptions), faster-whisper e normalização."""

    def setUp(self):
        from server.chat.audio_transcriber import AudioTranscriber
        self.transcriber = AudioTranscriber()

    def test_normalization_pt_br(self):
        """Normalização textual deve remover ruídos, corrigir pontuação e capitalização."""
        if hasattr(self.transcriber, "normalize_transcription"):
            raw = "  [ruído]  olá mundo do cockpit , como vai você ? [música]  "
            cleaned = self.transcriber.normalize_transcription(raw)
            self.assertNotIn("[ruído]", cleaned)
            self.assertNotIn("[música]", cleaned)
            self.assertTrue(cleaned.startswith("Olá"))
            self.assertIn("mundo do cockpit,", cleaned)
            self.assertTrue(cleaned.endswith("?"))
        else:
            self.fail("AudioTranscriber deve possuir método normalize_transcription.")

    @patch("urllib.request.urlopen")
    def test_omniroute_stt_routing_success(self, mock_urlopen):
        """Quando OmniRoute responder em /v1/audio/transcriptions, deve usar a transcrição de IA."""
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.read.return_value = b'{"text": "Criar um novo componente de dashboard para o Cockpit."}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        wav_data = generate_wav_bytes(duration_sec=0.5, sample_rate=16000, freq=440.0, volume=0.7)
        self.transcriber.omniroute_url = "http://localhost:20128/v1"

        if hasattr(self.transcriber, "_transcribe_omniroute"):
            res = self.transcriber._transcribe_omniroute(wav_data)
            self.assertIsNotNone(res)
            self.assertIn("componente de dashboard", res)
        else:
            self.fail("AudioTranscriber deve possuir suporte a transcrição via OmniRoute.")

    def test_faster_whisper_integration_if_present(self):
        """Se faster_whisper estiver disponível ou mockado, deve executar inferência local."""
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = "Executar testes de unidade agora"
        mock_model.transcribe.return_value = ([mock_segment], None)

        self.transcriber._external_stt = ("faster_whisper", mock_model)
        wav_data = generate_wav_bytes(duration_sec=0.5, sample_rate=16000, freq=440.0, volume=0.7)

        if hasattr(self.transcriber, "_transcribe_faster_whisper"):
            res = self.transcriber._transcribe_faster_whisper(wav_data)
            self.assertIsNotNone(res)
            self.assertIn("Executar testes de unidade agora", res)
        else:
            self.fail("AudioTranscriber deve possuir método _transcribe_faster_whisper.")


if __name__ == "__main__":
    unittest.main()
