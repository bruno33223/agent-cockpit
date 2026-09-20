"""
server/chat/zeus_engine.py: Fachada unificada e coordenador do Zeus Chat Engine.
Chief Architect: Function Calling tático, despacho de workers e telemetria de avatar.
"""

import json
import time
import uuid
import urllib.request
from typing import Dict, List, Any, Optional, Iterator, Tuple, Callable

try:
    from server.chat.constants import DEFAULT_ZEUS_SYSTEM_PROMPT, AVAILABLE_TOOLS, ZEUS_TOOLS
    from server.chat.vision import is_vision_model, validate_image_payload
    from server.chat.session_manager import SessionManager
    from server.chat.audio_transcriber import AudioTranscriber, extract_audio_from_multipart
    from server.chat.prompt_optimizer import PromptOptimizer
    from server.chat.providers import (
        stream_opencode, stream_omniroute, stream_ollama, stream_fallback, parse_think_tags
    )
    from server.chat.providers.utils import build_batch_synthesis_fallback, resolve_effective_backend
    from server.chat.avatar_telemetry import emit_avatar_state, AVATAR_STATES
    from server.chat.tool_dispatcher import (
        dispatch_subagent, run_test_suite, read_project_status, execute_zeus_tool
    )
except ImportError:
    from chat.constants import DEFAULT_ZEUS_SYSTEM_PROMPT, AVAILABLE_TOOLS, ZEUS_TOOLS
    from chat.vision import is_vision_model, validate_image_payload
    from chat.session_manager import SessionManager
    from chat.audio_transcriber import AudioTranscriber, extract_audio_from_multipart
    from chat.prompt_optimizer import PromptOptimizer
    from chat.providers import (
        stream_opencode, stream_omniroute, stream_ollama, stream_fallback, parse_think_tags
    )
    from chat.providers.utils import build_batch_synthesis_fallback, resolve_effective_backend
    from chat.avatar_telemetry import emit_avatar_state, AVATAR_STATES
    from chat.tool_dispatcher import (
        dispatch_subagent, run_test_suite, read_project_status, execute_zeus_tool
    )


class ZeusChatEngine:
    """Motor central do Zeus Chat: inferência, histórico, multimodalidade e telemetria."""

    def __init__(self, omniroute_url: str = "http://localhost:20128/v1", ollama_url: str = "http://127.0.0.1:11434"):
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
        transcription = self.stt_engine.transcribe(audio_bytes, hint=hint)
        return {"status": "ok", "transcription": transcription, "optimized_prompt": self.prompt_optimizer.optimize(transcription)}

    def extract_audio_from_multipart(self, raw_body: bytes, content_type: str) -> Tuple[bytes, Optional[str]]:
        return extract_audio_from_multipart(raw_body, content_type)

    def dispatch_subagent(self, task_description: str, target_slice: str = "", isolation_level: str = "worktree") -> Dict[str, Any]:
        return dispatch_subagent(task_description, target_slice, isolation_level)

    def run_test_suite(self, test_target: str = "all", run_mode: str = "fast") -> Dict[str, Any]:
        return run_test_suite(test_target, run_mode)

    def read_project_status(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        return read_project_status(project_id)

    def emit_avatar_state(self, state: str, session_id: str, callback: Optional[Callable] = None) -> Dict[str, Any]:
        return emit_avatar_state(state, session_id, callback)

    def check_omniroute_online(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.omniroute_url}/models", headers={"User-Agent": "ZeusChatEngine/1.0"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                return resp.getcode() == 200
        except Exception:
            return False

    def check_ollama_online(self) -> bool:
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
        broadcast_callback: Optional[Callable[[str, Dict[str, Any], Optional[str]], None]] = None,
        include_tools: bool = True
    ) -> Iterator[Dict[str, Any]]:
        """Geração streaming com emissão de eventos estruturados e telemetria do avatar."""
        start_time = time.time()
        session_id = session_id or str(uuid.uuid4())
        self.session_manager.append_message(session_id=session_id, role="user", content=message, images=images)

        effective_backend = resolve_effective_backend(backend, model_id, self.check_omniroute_online, self.check_ollama_online)
        acc_thinking, acc_content, acc_tools, acc_subagents = [], [], [], []
        token_counter, has_stream_error, has_spoken = 0, False, False

        def emit_event(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal token_counter
            event = {"type": event_type, "session_id": session_id, "timestamp": time.time(), **data}
            if event_type in ("content", "thinking") and data.get("text"):
                token_counter += max(1, len(data["text"].split()))
            if broadcast_callback:
                try:
                    broadcast_callback("ZEUS_CHAT_EVENT", event, None)
                except Exception:
                    pass
            return event

        # 1. Telemetria inicial do avatar: LISTENING -> THINKING
        yield emit_avatar_state("LISTENING", session_id, broadcast_callback)
        yield emit_avatar_state("THINKING", session_id, broadcast_callback)

        if effective_backend == "none":
            yield emit_event("error", {"error": "Nenhum motor de IA ativo.", "code": "NO_ACTIVE_BACKEND"})
            return

        effective_sys = system_prompt or DEFAULT_ZEUS_SYSTEM_PROMPT
        try:
            if effective_backend == "opencode":
                stream_gen = self._stream_opencode(session_id, message, model_id, images, effective_sys)
            elif effective_backend == "omniroute":
                clean_m = model_id[len("omniroute/"):] if model_id and model_id.startswith("omniroute/") else model_id
                stream_gen = self._stream_omniroute(session_id, message, clean_m, images, effective_sys, include_tools=include_tools)
            elif effective_backend == "ollama":
                clean_m = model_id[len("ollama/"):] if model_id and model_id.startswith("ollama/") else model_id
                stream_gen = self._stream_ollama(session_id, message, clean_m, effective_sys)
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
                    if not has_spoken:
                        has_spoken = True
                        yield emit_avatar_state("SPEAKING", session_id, broadcast_callback)
                    acc_content.append(ev.get("text", ""))
                elif t == "tool_call":
                    acc_tools.append(ev)
                    tool_name = str(ev.get("tool", "")).lower()
                    if any(w in tool_name for w in ("subagent", "spawn", "worker")):
                        yield emit_avatar_state("DISPATCHING_WORKER", session_id, broadcast_callback)
                    elif "test" in tool_name:
                        yield emit_avatar_state("TESTING", session_id, broadcast_callback)
                elif t == "subagent_spawn":
                    acc_subagents.append(ev)
                    yield emit_avatar_state("DISPATCHING_WORKER", session_id, broadcast_callback)
                elif t == "step_finish":
                    tok = ev.get("tokens", {})
                    if isinstance(tok, dict) and "total" in tok:
                        token_counter = tok["total"]
                elif t == "error":
                    has_stream_error = True
                yield ev

            if not has_stream_error:
                if not "".join(acc_content).strip() and acc_tools:
                    fb = build_batch_synthesis_fallback(acc_tools)
                    acc_content.append(fb)
                    yield emit_event("content", {"text": fb})

                elapsed = round(time.time() - start_time, 3)
                yield emit_event("done", {
                    "duration_seconds": elapsed, "tokens": token_counter, "finish_reason": "stop",
                    "backend": effective_backend, "model": model_id
                })
                yield emit_avatar_state("IDLE", session_id, broadcast_callback)
                self.session_manager.append_message(
                    session_id=session_id, role="assistant", content="".join(acc_content),
                    thinking="".join(acc_thinking) if acc_thinking else None,
                    tool_calls=acc_tools or None, subagents=acc_subagents or None,
                    metrics={"duration_seconds": elapsed, "tokens": token_counter, "backend": effective_backend, "model": model_id}
                )
        except Exception as e:
            yield emit_event("error", {"error": str(e), "code": "CHAT_STREAM_ERROR"})

    def stream_chat_sse(
        self, session_id: str, message: str, model_id: str = "auto", backend: str = "auto",
        images: Optional[List[str]] = None, system_prompt: Optional[str] = None,
        broadcast_callback: Optional[Callable] = None
    ) -> Iterator[str]:
        for event in self.stream_chat(session_id, message, model_id, backend, images, system_prompt, broadcast_callback):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    def _stream_omniroute(self, session_id: str, message: str, model_id: str, images=None, system_prompt=None, include_tools: bool = True):
        return stream_omniroute(self.omniroute_url, session_id, message, model_id, self.get_history(session_id), images, system_prompt, include_tools=include_tools)

    def _stream_ollama(self, session_id: str, message: str, model_id: str, system_prompt=None):
        return stream_ollama(self.ollama_url, session_id, message, model_id, self.get_history(session_id), system_prompt)

    def _stream_opencode(self, session_id: str, message: str, model_id: str, images=None, system_prompt=None):
        return stream_opencode(session_id, message, model_id, images, system_prompt)

    def _stream_fallback(self, session_id: str, message: str, images=None):
        return stream_fallback(session_id, message, images)


zeus_engine = ZeusChatEngine()
