"""
Pacote Local Builder do Agent Cockpit:
Execução de construção local, patching cirúrgico, circuit breaker e filas de workers.
"""

from .surgical_patcher import (
    SEARCH_REPLACE_REGEX,
    resolve_safe_worktree_path,
    apply_surgical_patch,
)
from .circuit_breaker import (
    build_local_prompt,
    call_local_llm,
    call_omniroute_llm,
    is_local_llm_recoverable_failure,
)
from .builder_service import (
    is_file_empty_or_blank,
    generate_scaffold_fallback,
    get_worker_queue_status,
    manage_local_model,
    LocalBuilder,
    execute_local_builder,
)

__all__ = [
    "SEARCH_REPLACE_REGEX",
    "resolve_safe_worktree_path",
    "apply_surgical_patch",
    "build_local_prompt",
    "call_local_llm",
    "call_omniroute_llm",
    "is_local_llm_recoverable_failure",
    "is_file_empty_or_blank",
    "generate_scaffold_fallback",
    "get_worker_queue_status",
    "manage_local_model",
    "LocalBuilder",
    "execute_local_builder",
]
