"""
server/chat/providers/__init__.py: Provedores de streaming de inferência para o Zeus Chat Engine.
"""

try:
    from server.chat.providers.opencode_stream import stream_opencode
    from server.chat.providers.omniroute_stream import stream_omniroute
    from server.chat.providers.ollama_stream import stream_ollama
    from server.chat.providers.fallback_stream import stream_fallback
    from server.chat.providers.utils import parse_think_tags
except ImportError:
    from chat.providers.opencode_stream import stream_opencode
    from chat.providers.omniroute_stream import stream_omniroute
    from chat.providers.ollama_stream import stream_ollama
    from chat.providers.fallback_stream import stream_fallback
    from chat.providers.utils import parse_think_tags

__all__ = [
    "stream_opencode",
    "stream_omniroute",
    "stream_ollama",
    "stream_fallback",
    "parse_think_tags",
]
