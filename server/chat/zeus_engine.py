"""
server/chat/zeus_engine.py: Fachada unificada e coordenador de orquestração do Zeus Chat.
"""

import json
import time
import uuid
import urllib.request
from typing import Dict, List, Any, Optional, Iterator, Tuple, Callable

try:
    from server.chat.constants import DEFAULT_ZEUS_SYSTEM_PROMPT, AVAILABLE_TOOLS, ZEUS_TOOLS
    from server.chat.vision import (
        VISION_MODEL_PATTERNS, VISION_REGEX, is_vision_model, validate_image_payload
    )
    from server.chat.session_manager import SessionManager
    from server.chat.audio_transcriber import AudioTranscriber, extract_audio_from_multipart
    from server.chat.prompt_optimizer import PromptOptimizer
    from server.chat.providers import (
        stream_opencode, stream_omniroute, stream_ollama, stream_fallback, parse_think_tags
    )
    from server.chat.providers.utils import build_batch_synthesis_fallback, resolve_effective_backend
except ImportError:
    from chat.constants import DEFAULT_ZEUS_SYSTEM_PROMPT, AVAILABLE_TOOLS, ZEUS_TOOLS
    from chat.vision import (
        VISION_MODEL_PATTERNS, VISION_REGEX, is_vision_model, validate_image_payload
    )
    from chat.session_manager import SessionManager
    from chat.audio_transcriber import AudioTranscriber, extract_audio_from_multipart
    from chat.prompt_optimizer import PromptOptimizer
    from chat.providers import (
        stream_opencode, stream_omniroute, stream_ollama, stream_fallback, parse_think_tags
    )
    from chat.providers.utils import build_batch_synthesis_fallback, resolve_effective_backend


class ZeusChatEngine:
    """Motor central do Zeus Chat coordenando inferência, histórico e multimodalidade."""

    def __init__(
        self,
        omniroute_url: str = "http://localhost:20128/v1",
        ollama_url: str = "http://127.0.0.1:11434"
    ):
        self.omniroute_url = omniroute_url.rstrip("/")
        self.ollama_url = ollama_url.rstrip("/")
        self.session_manager = SessionManager()
        self.stt_engine = AudioTranscriber()
        self.prompt_optimizer = PromptOptimizer()

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        return self.session_manager.get_history(session_id)

    def is_vision_model(self, model_id: Optional[str]) -> bool:
        return is_vision_model(model_id)

    def validate_image_payload(self, image_data: str) -> Dict[str, Any]:
        return validate_image_payload(image_data)

    def transcribe_and_optimize(self, audio_bytes: bytes, hint: Optional[str] = None) -> Dict[str, Any]:
        """Pipeline completo de transcrição rápida em RAM + otimização de prompt."""
        transcription = self.stt_engine.transcribe(audio_bytes, hint=hint)
        return {
            "status": "ok",
            "transcription": transcription,
            "optimized_prompt": self.prompt_optimizer.optimize(transcription)
        }

    def extract_audio_from_multipart(self, raw_body: bytes, content_type: str) -> Tuple[bytes, Optional[str]]:
        return extract_audio_from_multipart(raw_body, content_type)

    def check_omniroute_online(self) -> bool:
        """Verifica se OmniRoute está respondendo."""
        try:
            req = urllib.request.Request(f"{self.omniroute_url}/models", headers={"User-Agent": "ZeusChatEngine/1.0"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                return resp.getcode() == 200
        except Exception:
            return False

    def check_ollama_online(self) -> bool:
        """Verifica se Ollama local está respondendo."""
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags", headers={"User-Agent": "ZeusChatEngine/1.0"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                return resp.getcode() == 200
        except Exception:
            return False

    def stream_chat(
        self,
        session_id: str,
        message: str,
        model_id: str = "auto",
        backend: str = "auto",
        images: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        broadcast_callback: Optional[Callable[[str, Dict[str, Any], Optional[str]], None]] = None
    ) -> Iterator[Dict[str, Any]]:
        """Executa a geração com streaming de eventos estruturados."""
        start_time = time.time()
        session_id = session_id or str(uuid.uuid4())
        self.session_manager.append_message(session_id=session_id, role="user", content=message, images=images)

        effective_backend = resolve_effective_backend(
            backend, model_id, self.check_omniroute_online, self.check_ollama_online
        )

        acc_thinking, acc_content, acc_tools, acc_subagents = [], [], [], []
        token_counter = 0
        has_stream_error = False

        def emit_event(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal token_counter
            event = {"type": event_type, "session_id": session_id, "timestamp": time.time(), **data}
            text = data.get("text", "")
            if event_type in ("content", "thinking") and text:
                token_counter += max(1, len(text.split()))
            if broadcast_callback:
                try:
                    broadcast_callback("ZEUS_CHAT_EVENT", event, None)
                except Exception:
                    pass
            return event

        if effective_backend == "none":
            yield emit_event("error", {
                "error": "Nenhum motor de IA ativo. OpenCode, OmniRoute e Ollama estão indisponíveis no servidor.",
                "code": "NO_ACTIVE_BACKEND"
            })
            return

        effective_system_prompt = system_prompt or DEFAULT_ZEUS_SYSTEM_PROMPT

        try:
            if effective_backend == "opencode":
                stream_gen = self._stream_opencode(session_id, message, model_id, images, effective_system_prompt)
            elif effective_backend == "omniroute":
                clean_omni_model = model_id
                if clean_omni_model and clean_omni_model.startswith("omniroute/"):
                    clean_omni_model = clean_omni_model[len("omniroute/"):]
                stream_gen = self._stream_omniroute(session_id, message, clean_omni_model, images, effective_system_prompt)
            elif effective_backend == "ollama":
                clean_ol_model = model_id
                if clean_ol_model and clean_ol_model.startswith("ollama/"):
                    clean_ol_model = clean_ol_model[len("ollama/"):]
                stream_gen = self._stream_ollama(session_id, message, clean_ol_model, effective_system_prompt)
            elif effective_backend == "fallback":
                stream_gen = self._stream_fallback(session_id, message, images)
            else:
                yield emit_event("error", {"error": f"Backend desconhecido: '{effective_backend}'", "code": "UNKNOWN_BACKEND"})
                return

            for raw_event in stream_gen:
                ev = emit_event(raw_event["type"], raw_event)
                t = ev["type"]
                if t == "thinking":
                    acc_thinking.append(ev.get("text", ""))
                elif t == "content":
                    acc_content.append(ev.get("text", ""))
                elif t == "tool_call":
                    acc_tools.append(ev)
                elif t == "subagent_spawn":
                    acc_subagents.append(ev)
                elif t == "step_finish":
                    tok = ev.get("tokens", {})
                    if isinstance(tok, dict) and "total" in tok:
                        token_counter = tok["total"]
                elif t == "error":
                    has_stream_error = True
                yield ev

            if not has_stream_error:
                if not "".join(acc_content).strip() and acc_tools:
                    fallback_text = build_batch_synthesis_fallback(acc_tools)
                    acc_content.append(fallback_text)
                    yield emit_event("content", {"text": fallback_text})

                elapsed = round(time.time() - start_time, 3)
                yield emit_event("done", {
                    "duration_seconds": elapsed,
                    "tokens": token_counter,
                    "finish_reason": "stop",
                    "backend": effective_backend,
                    "model": model_id
                })
                self.session_manager.append_message(
                    session_id=session_id,
                    role="assistant",
                    content="".join(acc_content),
                    thinking="".join(acc_thinking) if acc_thinking else None,
                    tool_calls=acc_tools or None,
                    subagents=acc_subagents or None,
                    metrics={"duration_seconds": elapsed, "tokens": token_counter, "backend": effective_backend, "model": model_id}
                )

        except Exception as e:
            yield emit_event("error", {"error": str(e), "code": "CHAT_STREAM_ERROR"})

    def stream_chat_sse(
        self,
        session_id: str,
        message: str,
        model_id: str = "auto",
        backend: str = "auto",
        images: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        broadcast_callback: Optional[Callable] = None
    ) -> Iterator[str]:
        """Gera stream formatado para Server-Sent Events (SSE: data: {...}\\n\\n)."""
        for event in self.stream_chat(
            session_id=session_id,
            message=message,
            model_id=model_id,
            backend=backend,
            images=images,
            system_prompt=system_prompt,
            broadcast_callback=broadcast_callback
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    def _stream_omniroute(self, session_id: str, message: str, model_id: str, images=None, system_prompt=None):
        return stream_omniroute(self.omniroute_url, session_id, message, model_id, self.get_history(session_id), images, system_prompt)

    def _stream_ollama(self, session_id: str, message: str, model_id: str, system_prompt=None):
        return stream_ollama(self.ollama_url, session_id, message, model_id, self.get_history(session_id), system_prompt)

    def _stream_opencode(self, session_id: str, message: str, model_id: str, images=None, system_prompt=None):
        return stream_opencode(session_id, message, model_id, images, system_prompt)

    def _stream_fallback(self, session_id: str, message: str, images=None):
        return stream_fallback(session_id, message, images)

    def _parse_think_tags(self, text: str, current_in_think: bool):
        return parse_think_tags(text, current_in_think)


zeus_engine = ZeusChatEngine()
