"""
Módulo de workers do Agent Cockpit: PatchEngine e LocalLLMClient.
"""

from .patch_engine import PatchEngine, PatchBlock, PatchResult
from .local_llm_client import LocalLLMClient
from .ollama_process_manager import OllamaProcessManager
from .worker_queue import LocalWorkerQueue, local_worker_queue

__all__ = [
    "PatchEngine",
    "PatchBlock",
    "PatchResult",
    "LocalLLMClient",
    "OllamaProcessManager",
    "LocalWorkerQueue",
    "local_worker_queue",
]

