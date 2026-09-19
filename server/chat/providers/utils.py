"""
server/chat/providers/utils.py: Utilitários auxiliares de parsing e formatação para provedores de streaming.
"""

from typing import List, Tuple, Dict, Any, Callable, Optional


def parse_think_tags(
    text: str,
    current_in_think: bool
) -> List[Tuple[str, str, bool]]:
    """
    State machine simples para parsing de tags <think> e </think> no stream.
    Retorna lista de tuplas: (tipo_evento, texto, novo_estado_in_think).
    """
    results: List[Tuple[str, str, bool]] = []
    remaining = text
    in_think = current_in_think

    while remaining:
        if not in_think:
            if "<think>" in remaining:
                before, after = remaining.split("<think>", 1)
                if before:
                    results.append(("content", before, False))
                in_think = True
                remaining = after
            else:
                results.append(("content", remaining, False))
                break
        else:
            if "</think>" in remaining:
                before, after = remaining.split("</think>", 1)
                if before:
                    results.append(("thinking", before, True))
                in_think = False
                remaining = after
            else:
                results.append(("thinking", remaining, True))
                break

    return results


def build_batch_synthesis_fallback(accumulated_tools: List[Dict[str, Any]]) -> str:
    """Gera síntese estruturada em Markdown quando ações ocorrem sem conteúdo de texto emitido."""
    tool_count = len(accumulated_tools)
    tool_items = []
    for t in accumulated_tools[:10]:
        t_name = t.get("tool") or t.get("name") or "ação"
        t_cmd = t.get("command") or ""
        if t_cmd:
            clean_cmd = str(t_cmd).strip().replace("\n", " ")
            if len(clean_cmd) > 80:
                clean_cmd = clean_cmd[:77] + "..."
            tool_items.append(f"- `{t_name}`: `{clean_cmd}`")
        else:
            tool_items.append(f"- `{t_name}`")

    if tool_count > 10:
        tool_items.append(f"- ... e mais {tool_count - 10} operação(ões).")

    details_block = "\n".join(tool_items)
    return (
        f"⚡ *As ações e ferramentas solicitadas foram concluídas pelo agente ({tool_count} operações executadas).*\n\n"
        f"**Resumo das operações realizadas:**\n"
        f"{details_block}\n\n"
        f"*(O modelo encerrou o ciclo de ferramentas em modo batch sem emitir síntese textual adicional. "
        f"Todos os passos técnicos podem ser inspecionados no painel de ferramentas acima).*"
    )


def resolve_effective_backend(
    backend: Optional[str],
    model_id: Optional[str],
    is_omniroute_online: Callable[[], bool],
    is_ollama_online: Callable[[], bool]
) -> str:
    """Resolve o backend de inferência efetivo com base em prefixos, disponibilidade e modelo."""
    effective_backend = backend.lower() if backend else "auto"
    if effective_backend != "auto":
        return effective_backend

    if model_id and model_id.startswith("opencode/"):
        return "opencode"
    if model_id and model_id.startswith("omniroute/"):
        return "omniroute"
    if model_id and model_id.startswith("ollama/"):
        return "ollama"

    if is_omniroute_online():
        return "omniroute"
    if is_ollama_online():
        return "ollama"

    try:
        from server.opencode_manager import detect_binaries
        bins = detect_binaries()
        if bins.get("opencode", {}).get("installed"):
            return "opencode"
    except Exception:
        pass

    return "none"
