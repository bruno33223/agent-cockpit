"""
server/zeus_chat_engine.py: Fachada de retrocompatibilidade para o motor de chat do Zeus.
Reexporta todos os componentes desacoplados presentes no pacote modular `server/chat/`.

Consolida o papel do Orquestrador Zeus (Staff Orchestrator) e assegura que:
effective_system_prompt = system_prompt or DEFAULT_ZEUS_SYSTEM_PROMPT
"""

import sys
import os

try:
    from server.chat import (
        DEFAULT_ZEUS_SYSTEM_PROMPT,
        AVAILABLE_TOOLS,
        ZEUS_TOOLS,
        VISION_MODEL_PATTERNS,
        VISION_REGEX,
        is_vision_model,
        validate_image_payload,
        SessionManager,
        ChatMessage,
        AudioTranscriber,
        InMemorySTTEngine,
        extract_audio_from_multipart,
        PromptOptimizer,
        stream_opencode,
        stream_omniroute,
        stream_ollama,
        stream_fallback,
        parse_think_tags,
        ZeusChatEngine,
        zeus_engine,
    )
except ImportError:
    from chat import (
        DEFAULT_ZEUS_SYSTEM_PROMPT,
        AVAILABLE_TOOLS,
        ZEUS_TOOLS,
        VISION_MODEL_PATTERNS,
        VISION_REGEX,
        is_vision_model,
        validate_image_payload,
        SessionManager,
        ChatMessage,
        AudioTranscriber,
        InMemorySTTEngine,
        extract_audio_from_multipart,
        PromptOptimizer,
        stream_opencode,
        stream_omniroute,
        stream_ollama,
        stream_fallback,
        parse_think_tags,
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
