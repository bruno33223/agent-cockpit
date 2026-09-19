"""
Fachada de retrocompatibilidade para ferramentas do Local Builder.
Delega para a arquitetura desacoplada em server/tools/local_builder/.
"""

import os
import sys

BASE_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_SERVER_DIR not in sys.path:
    sys.path.insert(0, BASE_SERVER_DIR)

try:
    from tools.local_builder import (
        SEARCH_REPLACE_REGEX,
        resolve_safe_worktree_path,
        apply_surgical_patch,
        build_local_prompt,
        call_local_llm,
        call_omniroute_llm,
        is_local_llm_recoverable_failure,
        is_file_empty_or_blank,
        generate_scaffold_fallback,
        get_worker_queue_status,
        manage_local_model,
        LocalBuilder,
        execute_local_builder,
    )
except ImportError:
    from server.tools.local_builder import (
        SEARCH_REPLACE_REGEX,
        resolve_safe_worktree_path,
        apply_surgical_patch,
        build_local_prompt,
        call_local_llm,
        call_omniroute_llm,
        is_local_llm_recoverable_failure,
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
