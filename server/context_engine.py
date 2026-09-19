"""
server/context_engine.py
Context Engine & Token Budgeting para o Agent Cockpit.
Mapeado na Issue #41 / GAP 1: Governança de contexto, estimativa de tokens e truncamento de saídas.
"""

import os
import json
import math
import time
import uuid
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRATCH_DIR = os.path.join(BASE_DIR, "scratch")

# Capacidades padrão de janela de contexto por modelo (tokens)
MODEL_CONTEXT_WINDOWS: Dict[str, int] = {
    "default": 8192,
    "opencode/big-pickle": 32768,
    "claude-3-5-sonnet": 200000,
    "claude-3-haiku": 200000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "nemotron-3.5": 4096,
    "llama3": 8192,
    "deepseek-coder": 16384,
}


def estimate_tokens(content: Any, model_name: Optional[str] = None) -> int:
    """
    Estima a quantidade de tokens em um texto ou estrutura de dados.
    Aproximação heurística de ~4 caracteres por token.
    """
    if content is None:
        return 0
    if isinstance(content, str):
        if not content:
            return 0
        return max(1, math.ceil(len(content) / 4))
    if isinstance(content, (dict, list)):
        try:
            serialized = json.dumps(content, ensure_ascii=False)
            return max(1, math.ceil(len(serialized) / 4))
        except Exception:
            return max(1, math.ceil(len(str(content)) / 4))
    return max(1, math.ceil(len(str(content)) / 4))


class TokenBudgetManager:
    """Gerenciador de orçamento e limites da janela de contexto para modelos de IA."""

    def __init__(self, model_name: str = "default", custom_limits: Optional[Dict[str, int]] = None):
        self.model_name = model_name
        self.context_windows = dict(MODEL_CONTEXT_WINDOWS)
        if custom_limits:
            self.context_windows.update(custom_limits)

    def get_context_window(self, model_name: Optional[str] = None) -> int:
        """Retorna o tamanho total da janela de contexto para o modelo."""
        target = model_name or self.model_name
        return self.context_windows.get(target, self.context_windows.get("default", 8192))

    def estimate_tokens(self, content: Any) -> int:
        """Estima tokens para um dado conteúdo usando o modelo configurado."""
        return estimate_tokens(content, self.model_name)

    def allocate_budget(
        self,
        model_name: Optional[str] = None,
        system_pct: float = 0.15,
        tools_pct: float = 0.25,
        chat_history_pct: float = 0.40,
        reserve_pct: float = 0.20,
    ) -> Dict[str, int]:
        """
        Aloca o orçamento da janela de contexto entre os componentes do agente.
        Retorna mapa com orçamentos em tokens.
        """
        total = self.get_context_window(model_name)
        return {
            "total": total,
            "system_prompt": int(total * system_pct),
            "tools": int(total * tools_pct),
            "chat_history": int(total * chat_history_pct),
            "reserve": int(total * reserve_pct),
        }

    def check_budget_usage(
        self,
        used_tokens: int,
        model_name: Optional[str] = None,
        warning_threshold: float = 0.60,
    ) -> Dict[str, Any]:
        """
        Verifica o uso atual em relação à capacidade total do modelo.
        Sinaliza proximidade do limite (warning_threshold) e estouro de capacidade.
        """
        total = self.get_context_window(model_name)
        ratio = (used_tokens / total) if total > 0 else 1.0
        remaining = max(0, total - used_tokens)
        return {
            "used_tokens": used_tokens,
            "total_window": total,
            "remaining_tokens": remaining,
            "ratio": round(ratio, 4),
            "exceeded": used_tokens > total,
            "near_limit": ratio >= warning_threshold,
        }


def truncate_tool_output(
    output: str,
    max_tokens: int = 2000,
    scratch_dir: Optional[str] = None,
    command_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Trunca saídas extensas de ferramentas quando excedem o limite de tokens.
    Salva o log bruto completo em disco e retorna saída compactada com ponteiro file://.
    """
    orig_tokens = estimate_tokens(output)
    if orig_tokens <= max_tokens:
        return {
            "truncated": False,
            "content": output,
            "original_tokens": orig_tokens,
            "tokens": orig_tokens,
            "tokens_saved": 0,
            "log_path": None,
            "file_pointer": None,
        }

    target_scratch = os.path.abspath(scratch_dir or SCRATCH_DIR)
    os.makedirs(target_scratch, exist_ok=True)

    cmd_slug = f"{command_name}_" if command_name else "tool_output_"
    filename = f"{cmd_slug}{int(time.time())}_{uuid.uuid4().hex[:8]}.log"
    log_file_path = os.path.join(target_scratch, filename)

    with open(log_file_path, "w", encoding="utf-8") as f:
        f.write(output)

    file_pointer = f"file://{log_file_path}"

    # Reserva tokens para o aviso de truncamento
    notice = (
        f"\n\n... [OUTPUT TRUNCADO: {orig_tokens} tokens originais excederam o teto de {max_tokens} tokens. "
        f"Log completo salvo em: {file_pointer}] ...\n\n"
    )
    notice_tokens = estimate_tokens(notice)
    available_tokens = max(10, max_tokens - notice_tokens)
    head_tokens = available_tokens // 2
    tail_tokens = available_tokens - head_tokens

    head_chars = head_tokens * 4
    tail_chars = tail_tokens * 4

    compact_content = output[:head_chars] + notice + output[-tail_chars:]
    compact_tokens = estimate_tokens(compact_content)
    tokens_saved = max(0, orig_tokens - compact_tokens)

    return {
        "truncated": True,
        "content": compact_content,
        "original_tokens": orig_tokens,
        "tokens": compact_tokens,
        "tokens_saved": tokens_saved,
        "log_path": log_file_path,
        "file_pointer": file_pointer,
    }


def prune_chat_context(
    messages: List[Dict[str, Any]],
    max_tokens: int = 4000,
    retain_recent: int = 2,
    system_role: str = "system",
) -> Dict[str, Any]:
    """
    Condensa turnos de diálogo preservando o system prompt e as mensagens mais recentes.
    Substitui turnos antigos intermediários por mensagem compacta consolidada.
    """
    total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
    if total_tokens <= max_tokens:
        return {
            "pruned": False,
            "messages": messages,
            "tokens_saved": 0,
            "original_tokens": total_tokens,
            "pruned_tokens": total_tokens,
            "consolidated_count": 0,
        }

    system_msgs = [m for m in messages if m.get("role") == system_role]
    non_system = [m for m in messages if m.get("role") != system_role]

    if len(non_system) <= retain_recent:
        return {
            "pruned": False,
            "messages": messages,
            "tokens_saved": 0,
            "original_tokens": total_tokens,
            "pruned_tokens": total_tokens,
            "consolidated_count": 0,
        }

    middle_msgs = non_system[:-retain_recent]
    recent_msgs = non_system[-retain_recent:]

    middle_tokens = sum(estimate_tokens(m.get("content", "")) for m in middle_msgs)
    summary_text = (
        f"[CONTEXT_PRUNED] {len(middle_msgs)} turnos de diálogo anteriores consolidados "
        f"para respeitar a janela de contexto. (~{middle_tokens} tokens condensados)."
    )
    summary_msg = {"role": "system", "content": summary_text}

    pruned_messages = system_msgs + [summary_msg] + recent_msgs
    new_tokens = sum(estimate_tokens(m.get("content", "")) for m in pruned_messages)
    tokens_saved = max(0, total_tokens - new_tokens)

    return {
        "pruned": True,
        "messages": pruned_messages,
        "tokens_saved": tokens_saved,
        "original_tokens": total_tokens,
        "pruned_tokens": new_tokens,
        "consolidated_count": len(middle_msgs),
    }
