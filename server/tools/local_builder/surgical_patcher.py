import os
import re
from typing import Tuple, Optional
from state_store import db

SEARCH_REPLACE_REGEX = re.compile(
    r'<{5,9}\s*SEARCH\r?\n(.*?)\r?\n?={5,9}\r?\n(.*?)\r?\n?>{5,9}',
    re.DOTALL
)

def resolve_safe_worktree_path(slice_id: str, target_file: str, repo_root: Optional[str] = None) -> str:
    """
    Resolve com segurança o caminho de um arquivo dentro do workspace isolado .worktrees/{slice_id}/,
    impedindo ataques de Directory Traversal.
    """
    if os.path.isabs(target_file):
        raise ValueError(f"Caminho absoluto não permitido para target_file: {target_file}")

    target_norm = os.path.normpath(target_file)
    if target_norm == ".." or target_norm.startswith(".." + os.sep) or target_norm.startswith("../"):
        raise ValueError(f"Path traversal detectado: {target_file}")

    if repo_root:
        root_abs = os.path.abspath(repo_root)
        if root_abs.endswith(os.path.join(".worktrees", slice_id)) or (
            os.path.basename(root_abs) == slice_id and ".worktrees" in root_abs
        ):
            worktree_dir = root_abs
        else:
            worktree_dir = os.path.join(root_abs, ".worktrees", slice_id)
    else:
        cwd = os.path.abspath(os.getcwd())
        if cwd.endswith(os.path.join(".worktrees", slice_id)) or (
            os.path.basename(cwd) == slice_id and ".worktrees" in cwd
        ):
            worktree_dir = cwd
        else:
            proj_root = db.get_project_root()
            worktree_dir = os.path.join(os.path.abspath(proj_root), ".worktrees", slice_id) if proj_root else os.path.join(cwd, ".worktrees", slice_id)

    worktree_abs = os.path.abspath(worktree_dir)
    target_abs = os.path.abspath(os.path.join(worktree_abs, target_norm))

    if not (target_abs.startswith(worktree_abs + os.sep) or target_abs == worktree_abs):
        raise ValueError(f"Path traversal detectado: {target_file} está fora da worktree {worktree_abs}")

    return target_abs

def apply_surgical_patch(existing_content: str, patch_text: str) -> Tuple[str, int, str]:
    """
    Aplica cirurgicamente alterações ao conteúdo existente.
    Suporta:
    1. Criação direta de arquivo novo/vazio via bloco de código ou conteúdo limpo.
    2. Blocos cirúrgicos SEARCH/REPLACE (estilo Aider).
    3. Para arquivos curtos (<= 150 linhas), aceita reescrita completa via bloco de código.
    """
    if not existing_content.strip():
        matches = SEARCH_REPLACE_REGEX.findall(patch_text)
        if matches:
            replace_code = matches[0][1].replace("\r\n", "\n").strip()
            return replace_code + "\n", 1, f"+{len(replace_code.splitlines())} -0 lines"

        clean_text = patch_text.strip()
        fence_match = re.search(r'```(?:[a-zA-Z0-9_-]+)?\s*\n(.*?)\n```', clean_text, re.DOTALL)
        if fence_match:
            clean_text = fence_match.group(1).strip()
        clean_text = re.sub(r'<{5,9}\s*SEARCH.*?\n={5,9}\n?', '', clean_text, flags=re.DOTALL)
        clean_text = re.sub(r'>{5,9}', '', clean_text).strip()
        if not clean_text:
            raise ValueError("Resposta do modelo local vazia para criação do arquivo.")
        return clean_text + "\n", 1, f"+{len(clean_text.splitlines())} -0 lines"

    matches = SEARCH_REPLACE_REGEX.findall(patch_text)
    if matches:
        content = existing_content
        total_added, total_removed, hunks_applied = 0, 0, 0

        for search_block, replace_block in matches:
            norm_search = search_block.replace("\r\n", "\n")
            norm_replace = replace_block.replace("\r\n", "\n")
            norm_content = content.replace("\r\n", "\n")

            if not norm_search.strip():
                content = norm_content.rstrip() + "\n\n" + norm_replace.strip() + "\n"
                total_added += len(norm_replace.splitlines())
                hunks_applied += 1
                continue

            occurrences = norm_content.count(norm_search)
            if occurrences == 0:
                content_lines_raw = norm_content.splitlines(keepends=True)
                search_lines = norm_search.splitlines()
                n_search = len(search_lines)
                stripped_search = [sl.rstrip() for sl in search_lines]

                matching_indices = []
                if n_search > 0 and len(content_lines_raw) >= n_search:
                    for i in range(len(content_lines_raw) - n_search + 1):
                        window = [content_lines_raw[i + k].rstrip("\r\n").rstrip() for k in range(n_search)]
                        if window == stripped_search:
                            matching_indices.append(i)

                if len(matching_indices) == 1:
                    start_line = matching_indices[0]
                    end_line = start_line + n_search
                    start_char = sum(len(l) for l in content_lines_raw[:start_line])
                    end_char = sum(len(l) for l in content_lines_raw[:end_line])

                    matched_original = norm_content[start_char:end_char]
                    replacement = norm_replace
                    if matched_original.endswith("\n") and not replacement.endswith("\n"):
                        replacement = replacement + "\n"

                    content = norm_content[:start_char] + replacement + norm_content[end_char:]
                elif len(matching_indices) > 1:
                    raise ValueError(f"SEARCH block match failure: o bloco foi encontrado {len(matching_indices)} vezes no arquivo. O bloco deve ser único.")
                else:
                    raise ValueError(f"SEARCH block match failure: o bloco a ser substituído não foi encontrado no arquivo.\nSEARCH:\n{norm_search}")
            elif occurrences > 1:
                raise ValueError(f"SEARCH block match failure: o bloco foi encontrado {occurrences} vezes. O bloco deve ser único.")
            else:
                content = norm_content.replace(norm_search, norm_replace, 1)

            total_removed += len(norm_search.splitlines())
            total_added += len(norm_replace.splitlines())
            hunks_applied += 1

        return content, hunks_applied, f"+{total_added} -{total_removed} lines"

    if len(existing_content.splitlines()) <= 150:
        clean_text = patch_text.strip()
        fence_match = re.search(r'```(?:[a-zA-Z0-9_-]+)?\s*\n(.*?)\n```', clean_text, re.DOTALL)
        if fence_match:
            new_code = fence_match.group(1).strip() + "\n"
            if len(new_code.splitlines()) >= 3:
                return new_code, 1, f"+{len(new_code.splitlines())} -{len(existing_content.splitlines())} lines (whole-file update)"

    raise ValueError("Nenhum bloco SEARCH/REPLACE válido nem código de substituição encontrado na resposta do modelo.")
