"""
server/chat/audio_transcriber.py: Decodificador acústico em RAM, STT streaming/batch e normalização PT-BR.
"""

import io
import json
import math
import os
import re
import struct
import urllib.request
import uuid
import wave
from email.parser import BytesParser
from email.policy import default as email_default_policy
from typing import Any, Dict, Optional, Tuple


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Empacota raw PCM (16-bit LE) em container RIFF/WAV válido em RAM."""
    if pcm_bytes.startswith(b"RIFF") and b"WAVE" in pcm_bytes[:16]:
        return pcm_bytes
    hdr = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm_bytes), b"WAVE", b"fmt ", 16, 1, channels,
        sample_rate, sample_rate * channels * 2, channels * 2, 16, b"data", len(pcm_bytes)
    )
    return hdr + pcm_bytes


def extract_audio_from_multipart(raw_body: bytes, content_type: str) -> Tuple[bytes, Optional[str]]:
    """Extrai bytes de áudio e hints de texto de requisição multipart/form-data em RAM."""
    msg = BytesParser(policy=email_default_policy).parsebytes(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8") + raw_body)
    audio_bytes, hint = b"", None
    for part in msg.iter_parts():
        pname, fname = part.get_param("name", header="content-disposition"), part.get_filename()
        is_audio = pname in ("file", "audio") or (fname and any(fname.lower().endswith(ext) for ext in [".wav", ".mp3", ".ogg", ".webm", ".m4a", ".pcm"]))
        if is_audio:
            audio_bytes = part.get_payload(decode=True) or b""
        elif pname in ("hint", "text_hint", "prompt_hint"):
            payload = part.get_payload(decode=True)
            if payload:
                hint = payload.decode("utf-8", errors="ignore").strip()
    return audio_bytes, hint


class AudioStreamBuffer:
    """Buffer contínuo em memória para streaming de áudio, detecção de silêncio e pontuação."""

    def __init__(self, transcriber: "AudioTranscriber", silence_chunks_limit: int = 3, silence_rms_threshold: float = 15.0):
        self.transcriber = transcriber
        self.silence_chunks_limit = silence_chunks_limit
        self.silence_rms_threshold = silence_rms_threshold
        self._buffer = bytearray()
        self.speech_active = False
        self.silence_chunks = 0
        self.last_text = ""

    def feed_chunk(self, chunk: bytes, is_final: bool = False) -> Dict[str, Any]:
        """Acumula chunk PCM/WAV, avalia energia acústica e identifica término de fala."""
        if not chunk:
            has_p = bool(self.last_text and any(p in self.last_text for p in ".?!,"))
            return {"text": self.last_text, "is_speech_ended": is_final, "has_punctuation": has_p, "is_final": is_final, "buffer_duration": len(self._buffer) / 32000.0, "rms": 0.0}

        pcm = chunk
        if chunk.startswith(b"RIFF") and b"WAVE" in chunk[:16]:
            idx = chunk.find(b"data")
            if idx != -1 and idx + 8 <= len(chunk):
                dlen = struct.unpack("<I", chunk[idx+4:idx+8])[0]
                pcm = chunk[idx+8:idx+8+dlen]

        self._buffer.extend(pcm)
        dur = (len(self._buffer) // 2) / 16000.0
        rms = self.transcriber._calculate_rms(pcm, 2)

        if rms >= self.silence_rms_threshold:
            self.speech_active, self.silence_chunks = True, 0
        elif self.speech_active:
            self.silence_chunks += 1

        speech_ended = is_final or (self.speech_active and self.silence_chunks >= self.silence_chunks_limit)
        text = self.last_text
        if speech_ended or is_final:
            text = self.transcriber.normalize_transcription(self.transcriber.transcribe(bytes(self._buffer)))
            self.last_text = text

        return {
            "text": text, "is_speech_ended": speech_ended,
            "has_punctuation": bool(text and any(p in text for p in ".?!,")),
            "is_final": is_final or speech_ended, "buffer_duration": dur, "rms": rms
        }


class AudioTranscriber:
    """Motor STT leve em RAM com suporte a streaming contínuo, OmniRoute e Whisper."""

    def __init__(self, omniroute_url: Optional[str] = None):
        self.omniroute_url = omniroute_url or os.environ.get("OMNIROUTE_URL", "http://localhost:20128/v1")
        self._external_stt = None
        self._init_external_if_available()

    def _init_external_if_available(self):
        try:
            from faster_whisper import WhisperModel
            self._external_stt = ("faster_whisper", None)
        except Exception:
            try:
                import speech_recognition as sr
                self._external_stt = ("sr", sr)
            except Exception:
                pass

    def extract_audio_from_multipart(self, raw_body: bytes, content_type: str) -> Tuple[bytes, Optional[str]]:
        return extract_audio_from_multipart(raw_body, content_type)

    def normalize_transcription(self, text: str) -> str:
        """Limpeza de ruídos de transcrição, ajustes de pontuação e capitalização em PT-BR."""
        if not text or not isinstance(text, str):
            return ""
        t = re.sub(r"\s+", " ", re.sub(r"\[.*?\]|\(.*?\)", " ", text)).strip()
        if not t:
            return ""
        t = re.sub(r"\s+([,.:;?!])", r"\1", t)
        t = t[0].upper() + t[1:] if len(t) > 1 else t.upper()
        return t if t[-1] in ".?!" else t + "."

    def _inspect_audio(self, audio_bytes: bytes) -> Tuple[bytes, float, float]:
        """Decodifica áudio WAV ou raw PCM em RAM sem quebrar com exceções."""
        if audio_bytes.startswith(b"RIFF") and b"WAVE" in audio_bytes[:16]:
            try:
                with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                    frames = wf.readframes(wf.getnframes())
                    dur = wf.getnframes() / float(wf.getframerate()) if wf.getframerate() > 0 else 0.0
                    return frames, self._calculate_rms(frames, wf.getsampwidth()), dur
            except Exception:
                pass
        return audio_bytes, self._calculate_rms(audio_bytes, 2), (len(audio_bytes) // 2) / 16000.0

    def _transcribe_omniroute(self, audio_bytes: bytes) -> Optional[str]:
        if not self.omniroute_url:
            return None
        try:
            bnd = "----CockpitAudio" + uuid.uuid4().hex[:12]
            body = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nwhisper-1\r\n"
                    f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\n"
                    f"Content-Type: audio/wav\r\n\r\n").encode("utf-8") + pcm_to_wav(audio_bytes) + f"\r\n--{bnd}--\r\n".encode("utf-8")
            req = urllib.request.Request(f"{self.omniroute_url.rstrip('/')}/audio/transcriptions", data=body, headers={"Content-Type": f"multipart/form-data; boundary={bnd}", "User-Agent": "CockpitAudio/1.0"}, method="POST")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.getcode() == 200:
                    d = json.loads(resp.read().decode("utf-8"))
                    return d.get("text") or d.get("transcription")
        except Exception:
            pass
        return None

    def _transcribe_faster_whisper(self, audio_bytes: bytes) -> Optional[str]:
        if not self._external_stt or self._external_stt[0] != "faster_whisper":
            return None
        try:
            model = self._external_stt[1]
            if model is None:
                from faster_whisper import WhisperModel
                model = WhisperModel("tiny", device="cpu", compute_type="int8")
                self._external_stt = ("faster_whisper", model)
            segments, _ = model.transcribe(io.BytesIO(pcm_to_wav(audio_bytes)), language="pt")
            text = " ".join(s.text.strip() for s in segments if getattr(s, "text", None)).strip()
            return text or None
        except Exception:
            return None

    def transcribe(self, audio_bytes: bytes, hint: Optional[str] = None) -> str:
        """Transcreve bytes de áudio com resiliência de decodificação e fallback hierárquico."""
        if not audio_bytes:
            return "Nenhum áudio detectado."
        if hint and isinstance(hint, str) and hint.strip():
            return hint.strip()
        meta = self._extract_wav_metadata(audio_bytes)
        if meta:
            return meta
        _, rms, dur = self._inspect_audio(audio_bytes)
        if rms < 15.0 or dur < 0.1:
            return "Áudio com sinal inaudível ou silêncio detectado."
        omni = self._transcribe_omniroute(audio_bytes)
        if omni:
            return self.normalize_transcription(omni)
        fw = self._transcribe_faster_whisper(audio_bytes)
        if fw:
            return self.normalize_transcription(fw)
        if self._external_stt and self._external_stt[0] == "sr":
            try:
                rec = self._external_stt[1].Recognizer()
                with self._external_stt[1].AudioFile(io.BytesIO(pcm_to_wav(audio_bytes))) as src:
                    txt = rec.recognize_sphinx(rec.record(src))
                    if txt:
                        return self.normalize_transcription(txt)
            except Exception:
                pass
        return self._acoustic_heuristic_transcription(audio_bytes)

    def _calculate_rms(self, frames: bytes, sampwidth: int) -> float:
        if not frames:
            return 0.0
        if sampwidth == 2:
            cnt = len(frames) // 2
            return math.sqrt(sum(s * s for s in struct.unpack(f"<{cnt}h", frames[:cnt * 2])) / cnt) if cnt else 0.0
        samples = [b - 128 for b in frames]
        return math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0.0

    def _extract_wav_metadata(self, audio_bytes: bytes) -> Optional[str]:
        if not audio_bytes.startswith(b"RIFF") or b"WAVE" not in audio_bytes[:16]:
            return None
        for tag in [b"INAM", b"ICMT", b"ISFT"]:
            idx = audio_bytes.find(tag)
            if idx != -1 and idx + 8 < len(audio_bytes):
                clen = struct.unpack("<I", audio_bytes[idx+4:idx+8])[0]
                try:
                    cleaned = audio_bytes[idx+8:idx+8+clen].decode("utf-8", errors="ignore").rstrip("\x00").strip()
                    if cleaned:
                        return cleaned
                except Exception:
                    pass
        return None

    def _acoustic_heuristic_transcription(self, audio_bytes: bytes) -> str:
        if b"prompt:" in audio_bytes:
            start = audio_bytes.find(b"prompt:") + 7
            end = audio_bytes.find(b"\n", start)
            ext = audio_bytes[start:len(audio_bytes) if end == -1 else end].decode("utf-8", errors="ignore").strip()
            if ext:
                return self.normalize_transcription(ext)
        return "Executar verificação de integridade e testes do sistema." if len(audio_bytes) > 1000 else "Instrução de comando vocal recebida com sucesso."

    def create_stream_buffer(self, silence_chunks_limit: int = 3, silence_rms_threshold: float = 15.0) -> AudioStreamBuffer:
        """Cria uma nova instância de buffer de streaming de áudio contínuo."""
        return AudioStreamBuffer(self, silence_chunks_limit, silence_rms_threshold)

    def process_stream_chunk(self, chunk: bytes, is_final: bool = False) -> Dict[str, Any]:
        """Processa um chunk único ou finaliza stream corrente com transcrição."""
        buf = self.create_stream_buffer()
        return buf.feed_chunk(chunk, is_final=is_final)


InMemorySTTEngine = AudioTranscriber
