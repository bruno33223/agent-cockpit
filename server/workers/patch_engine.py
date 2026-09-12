"""
PatchEngine: Mecanismo seguro e atômico para aplicação de patches SEARCH/REPLACE.
"""

import os
import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union


@dataclass
class PatchBlock:
    search: str
    replace: str
    file_path: Optional[str] = None


@dataclass
class PatchResult:
    success: bool
    file_path: str
    diff: str
    additions: int
    deletions: int
    message: str = ""


class PatchEngine:
    SEARCH_MARKER = "<<<<<<< SEARCH"
    DIVIDER_MARKER = "======="
    REPLACE_MARKER = ">>>>>>>"

    def __init__(self, workspace_root: Union[str, Path] = "."):
        self.workspace_root = Path(workspace_root).resolve()

    def validate_path(self, file_path: Union[str, Path], workspace_root: Optional[Union[str, Path]] = None) -> Path:
        """
        Valida que file_path está contido dentro do workspace_root,
        rejeitando tentativas de path traversal fora dos limites permitidos.
        """
        root = Path(workspace_root).resolve() if workspace_root else self.workspace_root
        raw_path = Path(file_path)

        if raw_path.is_absolute():
            target_path = raw_path.resolve()
        else:
            target_path = (root / raw_path).resolve()

        try:
            target_path.relative_to(root)
        except ValueError:
            raise ValueError(f"Path traversal detectado ou caminho fora do workspace: {file_path}")

        return target_path

    def parse_blocks(self, patch_text: str) -> List[PatchBlock]:
        """
        Analisa o texto do patch contendo blocos SEARCH/REPLACE.
        Gera exceção se encontrar blocos mal formatados ou abertos sem fechamento.
        """
        lines = patch_text.splitlines(keepends=True)
        blocks: List[PatchBlock] = []
        state = "OUTSIDE"
        search_lines: List[str] = []
        replace_lines: List[str] = []

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped == self.SEARCH_MARKER:
                if state != "OUTSIDE":
                    raise ValueError(f"Bloco SEARCH aninhado ou mal formatado na linha {idx + 1}")
                state = "IN_SEARCH"
                search_lines = []
                replace_lines = []
            elif stripped == self.DIVIDER_MARKER:
                if state != "IN_SEARCH":
                    raise ValueError(f"Marcador ======= inesperado fora de bloco SEARCH na linha {idx + 1}")
                state = "IN_REPLACE"
            elif stripped.startswith(self.REPLACE_MARKER):
                if state != "IN_REPLACE":
                    raise ValueError(f"Marcador >>>>>>> inesperado fora de bloco REPLACE na linha {idx + 1}")
                state = "OUTSIDE"
                search_content = "".join(search_lines)
                replace_content = "".join(replace_lines)

                # Se a busca estiver vazia ou com apenas espaços em branco, trata como criação de arquivo
                if not search_content.strip():
                    search_content = ""

                blocks.append(PatchBlock(search=search_content, replace=replace_content))
            else:
                if state == "IN_SEARCH":
                    search_lines.append(line)
                elif state == "IN_REPLACE":
                    replace_lines.append(line)

        if state != "OUTSIDE":
            raise ValueError("Bloco de patch não finalizado com >>>>>>>")

        return blocks

    def apply_patch(
        self,
        file_path: Union[str, Path],
        patch_content: Union[str, List[PatchBlock]]
    ) -> PatchResult:
        """
        Aplica o patch de forma estritamente atômica com validação de match único,
        suporte à criação de novos arquivos (quando search está vazio) e rollback em caso de falha.
        """
        target_path = self.validate_path(file_path)

        if isinstance(patch_content, str):
            blocks = self.parse_blocks(patch_content)
        else:
            blocks = patch_content

        if not blocks:
            raise ValueError("Nenhum bloco de patch encontrado.")

        file_existed = target_path.exists()
        original_content = target_path.read_text(encoding="utf-8") if file_existed else None
        current_content = original_content

        # Processa todas as alterações em memória para garantir atomicidade
        for block_idx, block in enumerate(blocks):
            if block.search == "":
                # Criação ou substituição de arquivo completo
                current_content = block.replace
            else:
                if current_content is None:
                    raise ValueError(f"Arquivo alvo não encontrado para modificação: {file_path}")

                occurrences = current_content.count(block.search)
                matched_key = block.search

                if occurrences == 0:
                    # Fallback gracioso para divergências sutis de quebra de linha no final do bloco
                    trimmed = block.search.rstrip("\r\n")
                    if trimmed and current_content.count(trimmed) == 1:
                        matched_key = trimmed
                        occurrences = 1
                    else:
                        with_nl = block.search + "\n"
                        if current_content.count(with_nl) == 1:
                            matched_key = with_nl
                            occurrences = 1

                if occurrences == 0:
                    raise ValueError(
                        f"Padrão de busca não encontrado no arquivo {file_path} (bloco {block_idx + 1})"
                    )
                elif occurrences > 1:
                    raise ValueError(
                        f"Padrão de busca é ambíguo (encontradas {occurrences} ocorrências) no arquivo {file_path}"
                    )

                current_content = current_content.replace(matched_key, block.replace, 1)

        # Todos os blocos foram validados em memória com sucesso. Grava no disco.
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            target_path.write_text(current_content, encoding="utf-8")
        except Exception as write_err:
            # Rollback em caso de erro de gravação
            if file_existed and original_content is not None:
                target_path.write_text(original_content, encoding="utf-8")
            elif not file_existed and target_path.exists():
                target_path.unlink()
            raise write_err

        # Cálculo de diff unificado e estatísticas
        orig_lines = (original_content or "").splitlines(keepends=True)
        new_lines = (current_content or "").splitlines(keepends=True)
        diff_iter = difflib.unified_diff(
            orig_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}"
        )
        diff_str = "".join(diff_iter)
        additions = sum(1 for line in diff_str.splitlines() if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in diff_str.splitlines() if line.startswith("-") and not line.startswith("---"))

        return PatchResult(
            success=True,
            file_path=str(file_path),
            diff=diff_str,
            additions=additions,
            deletions=deletions,
            message="Patch aplicado com sucesso."
        )
