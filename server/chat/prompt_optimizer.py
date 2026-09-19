"""
server/chat/prompt_optimizer.py: Otimizador de prompts transformando fala informal em diretivas técnicas.
"""

import re
from typing import List, Tuple, Pattern


class PromptOptimizer:
    """
    Otimizador de prompts: transforma fala coloquial/informal em instruções
    técnicas concisas, estruturadas e prontas para execução por agentes de IA.
    """

    FILLER_WORDS: List[str] = [
        r"\bcara\b", r"\bmano\b", r"\bveja bem\b", r"\bolha só\b", r"\bolha\b",
        r"\btipo assim\b", r"\btipo\b", r"\bné\b", r"\bbeleza\b", r"\bentão\b",
        r"\baí\b", r"\bpor favor\b", r"\bme ajuda a\b", r"\bme ajuda aí\b",
        r"\bseguinte\b", r"\beu queria que você\b", r"\bvocê poderia\b",
        r"\bpreciso que\b", r"\bqueria saber se\b", r"\bserá que dá pra\b"
    ]

    INTENT_MAP: List[Tuple[Pattern, str]] = [
        (re.compile(r"\b(consert[ae]|arrum[ae]|corrij[ae]|t[aá] com bug|t[aá] dando erro|bug|quebrad[oa])\b", re.IGNORECASE), "Corrigir defeito"),
        (re.compile(r"\b(cri[ae]|implement[ae]|fa[zç][ae]?|adicion[ae]|coloc[ae]|bot[ae]|desenvolv[ae])\b", re.IGNORECASE), "Implementar funcionalidade"),
        (re.compile(r"\b(refator[ae]|limp[ae]|melhor[ae]|reorganiz[ae]|padroniz[ae])\b", re.IGNORECASE), "Refatorar componente"),
        (re.compile(r"\b(test[ae]|valid[ae]|rod[ae] os testes|verifiq[ue])\b", re.IGNORECASE), "Executar e validar testes"),
        (re.compile(r"\b(remov[ae]|delet[ae]|tir[ae]|exclu[ai])\b", re.IGNORECASE), "Remover elemento"),
        (re.compile(r"\b(otimiz[ae]|aceler[ae]|deix[ae] mais r[aá]pido)\b", re.IGNORECASE), "Otimizar desempenho"),
    ]

    def optimize(self, transcription: str) -> str:
        """Converte a transcrição em instrução técnica concisa e bem estruturada."""
        if not transcription or not transcription.strip():
            return "Nenhuma instrução informada para otimização."

        text = transcription.strip()

        # Remove vícios de linguagem e expressões vazias
        cleaned = text
        for filler in self.FILLER_WORDS:
            cleaned = re.sub(filler, "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Identifica a intenção primária
        intent_prefix = "Executar tarefa técnica"
        for pattern, label in self.INTENT_MAP:
            if pattern.search(cleaned):
                intent_prefix = label
                break

        # Limpeza gramatical básica e capitalização
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
        if not cleaned.endswith((".", "!", "?")):
            cleaned += "."

        # Formatação estruturada em prompt técnico conciso
        return f"[{intent_prefix}]: {cleaned}"
