"""
Módulo de workers do Agent Cockpit: PatchEngine e LocalLLMClient.
"""

from server.workers.patch_engine import PatchEngine, PatchBlock, PatchResult
from server.workers.local_llm_client import LocalLLMClient

__all__ = [
    "PatchEngine",
    "PatchBlock",
    "PatchResult",
    "LocalLLMClient",
]
