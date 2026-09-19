"""
server/chat: Pacote modular do motor de chat do Zeus (Agent Cockpit).
"""

from server.chat.constants import (
    DEFAULT_ZEUS_SYSTEM_PROMPT,
    AVAILABLE_TOOLS,
    ZEUS_TOOLS,
)
from server.chat.vision import (
    VISION_MODEL_PATTERNS,
    VISION_REGEX,
    is_vision_model,
    validate_image_payload,
)
from server.chat.session_manager import (
    SessionManager,
    ChatMessage,
)
from server.chat.audio_transcriber import (
    AudioTranscriber,
    InMemorySTTEngine,
    extract_audio_from_multipart,
)
from server.chat.prompt_optimizer import (
    PromptOptimizer,
)
from server.chat.providers import (
    stream_opencode,
    stream_omniroute,
    stream_ollama,
    stream_fallback,
    parse_think_tags,
)
from server.chat.zeus_engine import (
    ZeusChatEngine,
    zeus_engine,
)

__all__ = [
    "DEFAULT_ZEUS_SYSTEM_PROMPT",
    "AVAILABLE_TOOLS",
    "ZEUS_TOOLS",
    "VISION_MODEL_PATTERNS",
    "VISION_REGEX",
    "is_vision_model",
    "validate_image_payload",
    "SessionManager",
    "ChatMessage",
    "AudioTranscriber",
    "InMemorySTTEngine",
    "extract_audio_from_multipart",
    "PromptOptimizer",
    "stream_opencode",
    "stream_omniroute",
    "stream_ollama",
    "stream_fallback",
    "parse_think_tags",
    "ZeusChatEngine",
    "zeus_engine",
]
