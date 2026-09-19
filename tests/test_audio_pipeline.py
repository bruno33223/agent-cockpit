"""
tests/test_audio_pipeline.py: Validação de pipeline bi-direcional de áudio (TTS Streaming + STT Streaming).
Issue #43: [Voice Engine] Pipeline de Áudio Bi-direcional: Streaming STT com Whisper e Síntese TTS em Tempo Real
"""

import asyncio
import math
import os
import struct
import unittest
from unittest.mock import patch, MagicMock


def generate_pcm_chunk(duration_sec=0.1, sample_rate=16000, freq=440.0, volume=0.5) -> bytes:
    """Gera chunk de PCM 16-bit LE mono para teste de streaming."""
    num_samples = int(duration_sec * sample_rate)
    pcm_data = bytearray()
    for i in range(num_samples):
        val = int(volume * 32767.0 * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
        pcm_data.extend(struct.pack("<h", max(-32768, min(32767, val))))
    return bytes(pcm_data)


def generate_wav_chunk(duration_sec=0.1, sample_rate=16000, freq=440.0, volume=0.5) -> bytes:
    """Gera chunk empacotado em WAV RIFF."""
    pcm = generate_pcm_chunk(duration_sec, sample_rate, freq, volume)
    hdr = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16, 1, 1,
        sample_rate, sample_rate * 2, 2, 16, b"data", len(pcm)
    )
    return hdr + pcm


class TestAudioSynthesizerStreaming(unittest.IsolatedAsyncioTestCase):
    """Testes de síntese TTS com suporte a streaming de chunks e metadados de visemas/amplitude."""

    async def test_synthesize_stream_yields_chunks_and_metadata(self):
        """synthesize_stream deve gerar chunks de áudio acompanhados de amplitude e visemas."""
        from server.chat.audio_synthesizer import AudioSynthesizer

        synth = AudioSynthesizer(offline_mode=True)
        chunks = []
        async for audio_chunk, meta in synth.synthesize_stream("Olá mundo Cockpit", voice="pt-BR-FranciscaNeural"):
            chunks.append((audio_chunk, meta))

        self.assertGreater(len(chunks), 0, "Deve gerar ao menos um chunk de áudio.")
        for audio_chunk, meta in chunks:
            self.assertIsInstance(audio_chunk, bytes)
            self.assertGreater(len(audio_chunk), 0)
            self.assertIn("amplitude", meta)
            self.assertIsInstance(meta["amplitude"], float)
            self.assertGreaterEqual(meta["amplitude"], 0.0)
            self.assertIn("viseme", meta)
            self.assertIsInstance(meta["viseme"], str)
            self.assertIn("energy", meta)

    async def test_synthesize_to_bytes(self):
        """synthesize_to_bytes deve concatenar todos os chunks em um payload de áudio válido."""
        from server.chat.audio_synthesizer import AudioSynthesizer

        synth = AudioSynthesizer(offline_mode=True)
        audio_bytes = await synth.synthesize_to_bytes("Teste de síntese vocal", voice="pt-BR-FranciscaNeural")
        self.assertIsInstance(audio_bytes, bytes)
        self.assertGreater(len(audio_bytes), 0)

    async def test_synthesize_stream_default_mode(self):
        """synthesize_stream no modo padrão deve operar seja com edge-tts ou fallback gracioso."""
        from server.chat.audio_synthesizer import AudioSynthesizer

        synth = AudioSynthesizer(offline_mode=False)
        chunks = []
        async for audio_chunk, meta in synth.synthesize_stream("Teste de voz", voice="pt-BR-FranciscaNeural"):
            chunks.append((audio_chunk, meta))

        self.assertGreater(len(chunks), 0)
        self.assertIsInstance(chunks[0][0], bytes)
        self.assertIn("amplitude", chunks[0][1])
        self.assertIn("viseme", chunks[0][1])


class TestAudioSynthesizerFallback(unittest.IsolatedAsyncioTestCase):
    """Testes de resiliência e fallback gracioso quando edge-tts externo falha."""

    @patch("edge_tts.Communicate")
    async def test_fallback_when_edge_tts_fails(self, mock_communicate):
        """Quando edge-tts falhar por erro de rede/websocket, deve acionar fallback offline gracioso."""
        from server.chat.audio_synthesizer import AudioSynthesizer

        mock_instance = MagicMock()

        async def fail_stream():
            raise ConnectionError("Falha de conexão com os servidores TTS da Microsoft")
            yield  # pragma: no cover

        mock_instance.stream = fail_stream
        mock_communicate.return_value = mock_instance

        synth = AudioSynthesizer(offline_mode=False)
        chunks = []
        async for audio_chunk, meta in synth.synthesize_stream("Alerta do sistema", voice="pt-BR-FranciscaNeural"):
            chunks.append((audio_chunk, meta))

        self.assertGreater(len(chunks), 0, "Fallback offline deve produzir chunks mesmo com edge-tts offline.")
        audio_data = b"".join(c[0] for c in chunks)
        self.assertGreater(len(audio_data), 0)
        self.assertIn("viseme", chunks[0][1])
        self.assertIn("amplitude", chunks[0][1])

    @patch("edge_tts.Communicate")
    async def test_synthesize_to_bytes_fallback_on_network_error(self, mock_communicate):
        """synthesize_to_bytes deve retornar bytes sem propagar exceção em caso de falha externa."""
        from server.chat.audio_synthesizer import AudioSynthesizer

        mock_instance = MagicMock()

        async def fail_stream():
            raise TimeoutError("Timeout na síntese TTS")
            yield  # pragma: no cover

        mock_instance.stream = fail_stream
        mock_communicate.return_value = mock_instance

        synth = AudioSynthesizer(offline_mode=False)
        result = await synth.synthesize_to_bytes("Verificando resiliência.")
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)


class TestAudioTranscriberStreaming(unittest.TestCase):
    """Testes de acumulação e processamento contínuo de chunks de áudio no AudioTranscriber."""

    def setUp(self):
        from server.chat.audio_transcriber import AudioTranscriber
        self.transcriber = AudioTranscriber()

    def test_streaming_buffer_accumulation_and_speech_end(self):
        """Buffer de streaming deve acumular áudio, detectar fim de fala por silêncio e pontuar."""
        stream_buf = self.transcriber.create_stream_buffer(silence_chunks_limit=3)

        # 1. Envia chunks com sinal acústico audível (fala ativa)
        active_chunk = generate_pcm_chunk(duration_sec=0.1, freq=440.0, volume=0.7)
        res1 = stream_buf.feed_chunk(active_chunk, is_final=False)
        self.assertFalse(res1["is_speech_ended"])
        self.assertGreater(res1["buffer_duration"], 0.0)

        # 2. Envia mais um chunk ativo
        res2 = stream_buf.feed_chunk(active_chunk, is_final=False)
        self.assertFalse(res2["is_speech_ended"])

        # 3. Envia chunks de silêncio para simular pausa no microfone
        silent_chunk = generate_pcm_chunk(duration_sec=0.1, freq=0.0, volume=0.0)
        stream_buf.feed_chunk(silent_chunk, is_final=False)
        stream_buf.feed_chunk(silent_chunk, is_final=False)
        res_silence = stream_buf.feed_chunk(silent_chunk, is_final=False)

        # Após atingir limite de silêncio configurado, deve acusar término de fala
        self.assertTrue(res_silence["is_speech_ended"], "Deve acusar fim de fala após janela de silêncio.")
        self.assertTrue(res_silence["has_punctuation"], "Transcrição deve conter pontuação normalizada.")
        self.assertIsInstance(res_silence["text"], str)

    def test_streaming_buffer_with_wav_chunks(self):
        """Buffer deve aceitar chunks com cabeçalho RIFF/WAV sem estourar e processar normalmente."""
        stream_buf = self.transcriber.create_stream_buffer()
        wav_chunk = generate_wav_chunk(duration_sec=0.15, freq=500.0, volume=0.6)
        res = stream_buf.feed_chunk(wav_chunk, is_final=True)
        self.assertTrue(res["is_speech_ended"])
        self.assertTrue(res["is_final"])
        self.assertTrue(len(res["text"]) > 0)
        self.assertTrue(res["has_punctuation"])

    def test_transcriber_process_stream_chunk_direct(self):
        """Método de conveniência process_stream_chunk no AudioTranscriber."""
        chunk = generate_pcm_chunk(duration_sec=0.2, freq=440.0, volume=0.8)
        res = self.transcriber.process_stream_chunk(chunk, is_final=True)
        self.assertIn("text", res)
        self.assertIn("is_speech_ended", res)
        self.assertIn("has_punctuation", res)
        self.assertTrue(res["is_final"])


class TestLineCountConstraints(unittest.TestCase):
    """Garante que as regras rígidas de limites de linhas sejam rigorosamente respeitadas."""

    def test_strict_line_limits(self):
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        files_to_check = [
            (os.path.join(root_dir, "server", "chat", "audio_synthesizer.py"), 250),
            (os.path.join(root_dir, "server", "chat", "audio_transcriber.py"), 250),
            (os.path.join(root_dir, "tests", "test_audio_pipeline.py"), 400),
        ]
        for path, max_lines in files_to_check:
            self.assertTrue(os.path.exists(path), f"Arquivo não encontrado: {path}")
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            self.assertLessEqual(
                len(lines),
                max_lines,
                f"Arquivo {os.path.basename(path)} excedeu limite: {len(lines)} > {max_lines} linhas."
            )


if __name__ == "__main__":
    unittest.main()
