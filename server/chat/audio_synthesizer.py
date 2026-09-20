"""
server/chat/audio_synthesizer.py: Síntese de voz TTS com streaming, visemas, amplitude e fallback offline.
"""

import asyncio
import math
import struct
from typing import Any, AsyncGenerator, Dict, Optional, Tuple

DEFAULT_VOICE = "pt-BR-AntonioNeural"

VISEME_MAP: Dict[str, Tuple[str, int]] = {
    'a': ('viseme_aa', 2), 'á': ('viseme_aa', 2), 'à': ('viseme_aa', 2), 'ã': ('viseme_aa', 2), 'â': ('viseme_aa', 2),
    'e': ('viseme_ee', 6), 'é': ('viseme_ee', 6), 'ê': ('viseme_ee', 6),
    'i': ('viseme_ih', 7), 'í': ('viseme_ih', 7),
    'o': ('viseme_oh', 8), 'ó': ('viseme_oh', 8), 'ô': ('viseme_oh', 8), 'õ': ('viseme_oh', 8),
    'u': ('viseme_ou', 9), 'ú': ('viseme_ou', 9),
    'm': ('viseme_pbm', 21), 'b': ('viseme_pbm', 21), 'p': ('viseme_pbm', 21),
    'f': ('viseme_fv', 18), 'v': ('viseme_fv', 18),
    's': ('viseme_sz', 15), 'z': ('viseme_sz', 15), 'c': ('viseme_sz', 15), 'ç': ('viseme_sz', 15),
    't': ('viseme_td', 19), 'd': ('viseme_td', 19), 'n': ('viseme_td', 19), 'l': ('viseme_td', 19),
    'r': ('viseme_er', 5), 'j': ('viseme_ch', 16), 'g': ('viseme_kg', 20), 'k': ('viseme_kg', 20),
}


def text_to_viseme(text: str) -> Tuple[str, int]:
    """Mapeia fonema/letra do texto para identificador e ID de visema (SAPI)."""
    if not text:
        return ('viseme_sil', 0)
    for char in text.lower():
        if char in VISEME_MAP:
            return VISEME_MAP[char]
    return ('viseme_aa', 2)


def generate_offline_pcm(duration_sec: float = 0.1, sample_rate: int = 16000, freq: float = 300.0, volume: float = 0.5) -> bytes:
    """Gera sintetização acústica offline determinística em PCM 16-bit mono."""
    num_samples = int(duration_sec * sample_rate)
    pcm = bytearray()
    for i in range(num_samples):
        t = i / sample_rate
        sample = volume * 32767.0 * (0.7 * math.sin(2.0 * math.pi * freq * t) + 0.3 * math.sin(2.0 * math.pi * (freq * 1.5) * t))
        val = int(max(-32768, min(32767, sample)))
        pcm.extend(struct.pack("<h", val))
    return bytes(pcm)


class AudioSynthesizer:
    """Provedor de síntese Text-to-Speech (TTS) com suporte a edge-tts e fallback offline."""

    def __init__(self, default_voice: str = DEFAULT_VOICE, offline_mode: bool = False):
        self.default_voice = default_voice
        self.offline_mode = offline_mode

    def _calc_chunk_dynamics(self, chunk: bytes) -> Tuple[float, float]:
        """Calcula amplitude normalizada (0.0-1.0) e energia acústica a partir de bytes de áudio."""
        if not chunk:
            return 0.0, 0.0
        sample_len = min(1024, len(chunk))
        sub = chunk[:sample_len]
        dev = sum(abs(b - 128) for b in sub) / sample_len
        amplitude = min(1.0, dev / 64.0)
        energy = amplitude * 100.0
        return round(amplitude, 3), round(energy, 2)

    async def _mock_synthesize_stream(
        self, text: str, voice: str = DEFAULT_VOICE
    ) -> AsyncGenerator[Tuple[bytes, Dict[str, Any]], None]:
        """Gera streaming sintético offline para resiliência quando serviço externo indisponível."""
        words = text.strip().split() if text and text.strip() else ["Cockpit"]
        total = len(words)
        for idx, word in enumerate(words):
            viseme_name, viseme_id = text_to_viseme(word)
            pcm_chunk = generate_offline_pcm(duration_sec=0.1, freq=280.0 + (idx % 3) * 40.0)
            amp, energy = self._calc_chunk_dynamics(pcm_chunk)
            is_last = (idx == total - 1)
            meta = {
                "amplitude": max(0.2, amp),
                "energy": max(20.0, energy),
                "viseme": viseme_name,
                "viseme_id": viseme_id,
                "text": word,
                "is_final": is_last,
                "offset": idx * 100,
                "duration": 100,
            }
            yield pcm_chunk, meta
            await asyncio.sleep(0.005)

    async def synthesize_stream(
        self, text: str, voice: str = DEFAULT_VOICE
    ) -> AsyncGenerator[Tuple[bytes, Dict[str, Any]], None]:
        """Streaming de chunks de áudio e metadados de visemas/amplitude em tempo real."""
        v = voice or self.default_voice
        if self.offline_mode:
            async for item in self._mock_synthesize_stream(text, v):
                yield item
            return

        try:
            import edge_tts
            comm = edge_tts.Communicate(text, v)
            curr_word = ""
            curr_viseme = ("viseme_aa", 2)
            received_any = False
            buffered_chunk = None

            async for msg in comm.stream():
                mtype = msg.get("type")
                if mtype in ("WordBoundary", "SentenceBoundary"):
                    curr_word = msg.get("text", "")
                    curr_viseme = text_to_viseme(curr_word)
                elif mtype == "audio":
                    received_any = True
                    raw = msg.get("data", b"")
                    if raw:
                        amp, energy = self._calc_chunk_dynamics(raw)
                        meta = {
                            "amplitude": amp,
                            "energy": energy,
                            "viseme": curr_viseme[0],
                            "viseme_id": curr_viseme[1],
                            "text": curr_word,
                            "is_final": False,
                            "offset": msg.get("offset", 0),
                            "duration": msg.get("duration", 0),
                        }
                        if buffered_chunk:
                            yield buffered_chunk
                        buffered_chunk = (raw, meta)

            if buffered_chunk:
                buffered_chunk[1]["is_final"] = True
                yield buffered_chunk

            if not received_any:
                raise RuntimeError("Nenhum áudio gerado pelo serviço edge-tts.")
        except Exception:
            async for item in self._mock_synthesize_stream(text, v):
                yield item

    async def synthesize_to_bytes(self, text: str, voice: str = DEFAULT_VOICE) -> bytes:
        """Sintetiza áudio completo em memória e retorna bytes concatenados."""
        chunks = []
        async for audio_chunk, _ in self.synthesize_stream(text, voice=voice):
            chunks.append(audio_chunk)
        return b"".join(chunks)

    def synthesize_to_bytes_sync(self, text: str, voice: str = DEFAULT_VOICE) -> bytes:
        """Wrapper síncrono para integração rápida em contextos bloqueantes."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(asyncio.run, self.synthesize_to_bytes(text, voice)).result()
            return loop.run_until_complete(self.synthesize_to_bytes(text, voice))
        except Exception:
            return asyncio.run(self.synthesize_to_bytes(text, voice))
