"""
Módulo de workers do Agent Cockpit: PatchEngine e LocalLLMClient.
"""

from server.workers.patch_engine import PatchEngine, PatchBlock, PatchResult
from server.workers.local_llm_client import LocalLLMClient
from server.workers.ollama_process_manager import OllamaProcessManager

__all__ = [
    "PatchEngine",
    "PatchBlock",
    "PatchResult",
    "LocalLLMClient",
    "OllamaProcessManager",
]
