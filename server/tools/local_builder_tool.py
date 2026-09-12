import os
import re
import sys
import time
import json
import urllib.request
from typing import Dict, List, Any, Optional, Tuple

# Garante path para state_store
BASE_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_SERVER_DIR not in sys.path:
    sys.path.insert(0, BASE_SERVER_DIR)

from state_store import db

SEARCH_REPLACE_REGEX = re.compile(
    r'<{7}\s*SEARCH\r?\n(.*?)\r?\n?={7}\r?\n(.*?)\r?\n?>{7}',
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

    # Determina o diretório base da worktree
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
            # Tenta encontrar raiz do repo a partir do estado ou .git
            proj_root = db.get_project_root()
            if proj_root:
                worktree_dir = os.path.join(os.path.abspath(proj_root), ".worktrees", slice_id)
            else:
                worktree_dir = os.path.join(cwd, ".worktrees", slice_id)

    worktree_abs = os.path.abspath(worktree_dir)
    target_abs = os.path.abspath(os.path.join(worktree_abs, target_norm))

    # Validação rigorosa de pertencimento
    if not (target_abs.startswith(worktree_abs + os.sep) or target_abs == worktree_abs):
        raise ValueError(f"Path traversal detectado: {target_file} está fora da worktree {worktree_abs}")

    return target_abs

def apply_surgical_patch(existing_content: str, patch_text: str) -> Tuple[str, int, str]:
    """
    Aplica cirurgicamente blocos SEARCH/REPLACE (estilo Aider) ao conteúdo existente.
    Garante atomicidade total: se qualquer bloco falhar o match, lança ValueError sem alterar o arquivo.
    """
    matches = SEARCH_REPLACE_REGEX.findall(patch_text)
    if not matches:
        # Se não encontrou blocos SEARCH/REPLACE formais mas o arquivo é novo/vazio
        if not existing_content.strip():
            lines_added = len(patch_text.splitlines())
            return patch_text, 1, f"+{lines_added} -0 lines"
        raise ValueError("Nenhum bloco SEARCH/REPLACE válido encontrado na resposta do modelo.")

    content = existing_content
    total_added = 0
    total_removed = 0
    hunks_applied = 0

    for search_block, replace_block in matches:
        # Normaliza quebras de linha
        norm_search = search_block.replace("\r\n", "\n")
        norm_replace = replace_block.replace("\r\n", "\n")
        norm_content = content.replace("\r\n", "\n")

        if not norm_search:
            # Bloco de inserção inicial em arquivo vazio
            if not norm_content.strip():
                content = norm_replace
                total_added += len(norm_replace.splitlines())
                hunks_applied += 1
                continue
            else:
                raise ValueError("Bloco SEARCH vazio não permitido em arquivos não vazios.")

        occurrences = norm_content.count(norm_search)
        if occurrences == 0:
            # Tenta com strip de trailing whitespace em cada linha
            search_lines = [l.rstrip() for l in norm_search.splitlines()]
            clean_search = "\n".join(search_lines)
            content_lines = [l.rstrip() for l in norm_content.splitlines()]
            clean_content = "\n".join(content_lines)
            
            if clean_content.count(clean_search) == 1:
                idx = clean_content.find(clean_search)
                # Reconstitui substituição
                content = norm_content[:idx] + norm_replace + norm_content[idx + len(clean_search):]
            else:
                raise ValueError(f"SEARCH block match failure: o bloco a ser substituído não foi encontrado no arquivo.\nSEARCH:\n{norm_search}")
        elif occurrences > 1:
            raise ValueError(f"SEARCH block match failure: o bloco foi encontrado {occurrences} vezes. O bloco deve ser único.")
        else:
            content = norm_content.replace(norm_search, norm_replace, 1)

        removed_lines = len(norm_search.splitlines())
        added_lines = len(norm_replace.splitlines())
        total_removed += removed_lines
        total_added += added_lines
        hunks_applied += 1

    diff_summary = f"+{total_added} -{total_removed} lines"
    return content, hunks_applied, diff_summary

def build_local_prompt(
    instruction: str,
    target_file: str,
    existing_content: str,
    context_content: Optional[str] = None,
    error_feedback: Optional[str] = None
) -> str:
    """Constrói o prompt cirúrgico para o LLM local de 7B no padrão SEARCH/REPLACE."""
    prompt_parts = [
        "Você é um Local Coder cirúrgico. Implemente a instrução solicitada modificando o arquivo fornecido.",
        "REGRAS ESTRITAS:",
        "1. Responda EXCLUSIVAMENTE com um ou mais blocos SEARCH/REPLACE.",
        "2. Formato obrigatório:",
        "<<<<<<< SEARCH",
        "código original existente no arquivo a ser substituído",
        "=======",
        "novo código modificado",
        ">>>>>>>",
        "3. O código dentro de SEARCH deve ser idêntico ao código atual do arquivo (incluindo indentação).",
        "4. NÃO inclua explicações, comentários fora do código ou tags de markdown (como ```python).",
        f"\nArquivo Alvo: {target_file}",
        f"\nInstrução:\n{instruction}"
    ]

    if error_feedback:
        prompt_parts.append(f"\nFeedback de Erros da Tentativa Anterior:\n{error_feedback}")

    if context_content:
        prompt_parts.append(f"\nArquivos de Contexto (Apenas Leitura):\n{context_content}")

    prompt_parts.append(f"\nConteúdo Atual de {target_file}:\n```\n{existing_content}\n```")
    prompt_parts.append("\nGere os blocos SEARCH/REPLACE:")

    return "\n".join(prompt_parts)

def call_local_llm(
    instruction: str,
    target_file: str,
    existing_content: str,
    context_content: Optional[str] = None,
    error_feedback: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Chama o modelo local via API Ollama / llama.cpp."""
    cfg = config or {}
    endpoint = cfg.get("endpoint", "http://127.0.0.1:11434").rstrip("/")
    model = cfg.get("model", "qwen2.5-coder:7b-instruct-q4_k_m")

    prompt = build_local_prompt(
        instruction=instruction,
        target_file=target_file,
        existing_content=existing_content,
        context_content=context_content,
        error_feedback=error_feedback
    )

    url = f"{endpoint}/api/generate"
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.95
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    start_t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            patch_text = data.get("response", "")
            eval_count = data.get("eval_count") or max(len(patch_text.split()), 1)
            duration_ms = int((time.time() - start_t) * 1000)
            return {
                "patch": patch_text,
                "tokens": eval_count,
                "duration_ms": max(duration_ms, 1)
            }
    except Exception as e:
        raise RuntimeError(f"Falha na inferência do modelo local Ollama ({url}): {str(e)}")

def execute_local_builder(
    slice_id: str,
    instruction: str,
    target_file: str,
    context_files: Optional[List[str]] = None,
    error_feedback: Optional[str] = None,
    repo_root: Optional[str] = None,
    project_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delega a implementação física de código para o LLM local dentro da worktree isolada da fatia
    (.worktrees/{slice_id}/) usando patching cirúrgico SEARCH/REPLACE e circuit breaker.
    """
    cfg = db.get_local_worker_config(project_id=project_id)
    threshold = cfg.get("circuit_breaker_threshold", 2)
    attempts = db.get_local_worker_attempts(slice_id, project_id=project_id)

    # Circuit breaker check: limite de 2 tentativas consecutivas por fatia
    if attempts >= threshold:
        return {
            "status": "ESCALATION_REQUIRED",
            "slice_id": slice_id,
            "reason": "local_worker_threshold_exceeded",
            "last_error": error_feedback or f"Circuit breaker acionado: limite de {threshold} tentativas consecutivas atingido para '{slice_id}'."
        }

    start_time = time.time()
    try:
        target_abs = resolve_safe_worktree_path(slice_id, target_file, repo_root=repo_root)

        # Lê conteúdo existente se houver
        existing_content = ""
        if os.path.exists(target_abs):
            with open(target_abs, "r", encoding="utf-8", errors="ignore") as f:
                existing_content = f.read()

        # Lê arquivos de contexto se fornecidos
        context_data = []
        if context_files:
            for cf in context_files:
                try:
                    c_abs = resolve_safe_worktree_path(slice_id, cf, repo_root=repo_root)
                    if os.path.exists(c_abs):
                        with open(c_abs, "r", encoding="utf-8", errors="ignore") as f:
                            context_data.append(f"--- Arquivo de Contexto: {cf} ---\n{f.read(4000)}")
                except Exception:
                    pass
        context_str = "\n\n".join(context_data) if context_data else None

        # Executa inferência do LLM local
        llm_res = call_local_llm(
            instruction=instruction,
            target_file=target_file,
            existing_content=existing_content,
            context_content=context_str,
            error_feedback=error_feedback,
            config=cfg
        )

        patch_text = llm_res.get("patch", "")
        tokens_generated = llm_res.get("tokens", 0)
        execution_time_ms = llm_res.get("duration_ms", int((time.time() - start_time) * 1000))

        # Aplica o patch cirúrgico atomicamente
        new_content, hunks, diff_summary = apply_surgical_patch(existing_content, patch_text)

        # Garante diretórios pais e grava arquivo no disco
        os.makedirs(os.path.dirname(target_abs), exist_ok=True)
        with open(target_abs, "w", encoding="utf-8") as f:
            f.write(new_content)

        return {
            "status": "DELIVERED",
            "slice_id": slice_id,
            "target_file": target_file,
            "hunks_applied": hunks,
            "diff_summary": diff_summary,
            "execution_time_ms": max(execution_time_ms, 1),
            "local_tokens_generated": tokens_generated
        }
    except Exception as e:
        db.increment_local_worker_attempts(slice_id, project_id=project_id)
        current_attempts = db.get_local_worker_attempts(slice_id, project_id=project_id)
        if current_attempts >= threshold:
            return {
                "status": "ESCALATION_REQUIRED",
                "slice_id": slice_id,
                "reason": "local_worker_threshold_exceeded",
                "last_error": str(e)
            }
        raise e

def manage_local_model(
    action: str = "status",
    model_name: Optional[str] = None,
    endpoint: Optional[str] = None,
    project_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Gerencia o modelo e runtime local (Ollama/llama.cpp) para o Local Builder:
    consulta status, lista modelos instalados, seleciona o modelo ativo ou solicita pull.
    """
    cfg = db.get_local_worker_config(project_id=project_id)
    base_endpoint = (endpoint or cfg.get("endpoint", "http://127.0.0.1:11434")).rstrip("/")

    if action == "status":
        is_online = False
        try:
            req = urllib.request.Request(f"{base_endpoint}/api/version")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    is_online = True
        except Exception:
            is_online = False

        return {
            "status": "ONLINE" if is_online else "OFFLINE",
            "current_model": cfg.get("model", "qwen2.5-coder:7b-instruct-q4_k_m"),
            "endpoint": base_endpoint,
            "provider": cfg.get("provider", "ollama"),
            "circuit_breaker_threshold": cfg.get("circuit_breaker_threshold", 2)
        }

    elif action == "list":
        models = []
        try:
            req = urllib.request.Request(f"{base_endpoint}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") if isinstance(m, dict) else str(m) for m in data.get("models", [])]
        except Exception:
            models = cfg.get("available_models", [cfg.get("model", "qwen2.5-coder:7b-instruct-q4_k_m")])

        return {
            "status": "SUCCESS",
            "models": models,
            "current_model": cfg.get("model", "qwen2.5-coder:7b-instruct-q4_k_m")
        }

    elif action == "select":
        if not model_name:
            raise ValueError("model_name é obrigatório para a ação 'select'")
        db.set_local_worker_config({"model": model_name}, project_id=project_id)
        return {
            "status": "SELECTED",
            "model": model_name
        }

    elif action == "pull":
        if not model_name:
            raise ValueError("model_name é obrigatório para a ação 'pull'")
        try:
            req = urllib.request.Request(
                f"{base_endpoint}/api/pull",
                data=json.dumps({"name": model_name, "stream": False}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=600) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
            return {
                "status": "PULLED",
                "model": model_name,
                "details": res_data
            }
        except Exception as e:
            return {
                "status": "PULL_STARTED",
                "model": model_name,
                "warning": f"Comunicação com endpoint de pull: {str(e)}"
            }

    else:
        raise ValueError(f"Ação desconhecida para manage_local_model: '{action}'. Use status, list, select ou pull.")
