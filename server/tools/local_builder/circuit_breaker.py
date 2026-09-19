import os
import sys
import time
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

def build_local_prompt(
    instruction: str,
    target_file: str,
    existing_content: str,
    context_content: Optional[str] = None,
    error_feedback: Optional[str] = None
) -> str:
    """Constrói o prompt otimizado para o LLM local no padrão Direct / SEARCH/REPLACE."""
    if not existing_content.strip():
        parts = [
            "Você é um engenheiro de software sênior. Crie o código completo para o arquivo alvo solicitado.",
            f"\nArquivo Alvo: {target_file}", f"\nInstrução:\n{instruction}"
        ]
        if error_feedback:
            parts.append(f"\nFeedback de Erros da Tentativa Anterior:\n{error_feedback}")
        if context_content:
            parts.append(f"\nArquivos de Contexto (Apenas Leitura):\n{context_content}")
        parts.append("\nResponda EXCLUSIVAMENTE com o código completo do arquivo dentro de um bloco markdown:\n```\n[código completo aqui]\n```")
        return "\n".join(parts)

    if len(existing_content.splitlines()) <= 150:
        parts = [
            "Você é um engenheiro de software sênior. Modifique o arquivo alvo de acordo com a instrução.",
            f"\nArquivo Alvo: {target_file}", f"\nInstrução:\n{instruction}",
            f"\nConteúdo Atual de {target_file}:\n```\n{existing_content}\n```"
        ]
        if error_feedback:
            parts.append(f"\nFeedback de Erros da Tentativa Anterior:\n{error_feedback}")
        if context_content:
            parts.append(f"\nArquivos de Contexto (Apenas Leitura):\n{context_content}")
        parts.append("\nVocê pode responder com:")
        parts.append("Opção 1: O código COMPLETO atualizado do arquivo dentro de um bloco markdown ```:\n```\n[código completo atualizado]\n```")
        parts.append("Opção 2: OU blocos SEARCH/REPLACE cirúrgicos:\n<<<<<<< SEARCH\n[código original a substituir]\n=======\n[novo código]\n>>>>>>>")
        return "\n".join(parts)

    parts = [
        "Você é um Local Coder cirúrgico. Implemente a instrução solicitada modificando o arquivo fornecido.",
        "REGRAS ESTRITAS:\n1. Responda EXCLUSIVAMENTE com um ou mais blocos SEARCH/REPLACE.",
        "2. Formato obrigatório:\n<<<<<<< SEARCH\ncódigo original existente\n=======\nnovo código\n>>>>>>>",
        "3. O código dentro de SEARCH deve ser idêntico ao código atual do arquivo (incluindo indentação).",
        "4. NÃO inclua explicações ou comentários fora do código.",
        f"\nArquivo Alvo: {target_file}", f"\nInstrução:\n{instruction}"
    ]
    if error_feedback:
        parts.append(f"\nFeedback de Erros da Tentativa Anterior:\n{error_feedback}")
    if context_content:
        parts.append(f"\nArquivos de Contexto (Apenas Leitura):\n{context_content}")
    parts.append(f"\nConteúdo Atual de {target_file}:\n```\n{existing_content}\n```\nGere os blocos SEARCH/REPLACE:")
    return "\n".join(parts)

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
    model = cfg.get("model", "qwen2.5-coder:7b")
    prompt = build_local_prompt(instruction, target_file, existing_content, context_content, error_feedback)
    url = f"{endpoint}/api/generate"

    try:
        from workers.ollama_client import calculate_dynamic_num_ctx, DEFAULT_NUM_CTX
    except ImportError:
        DEFAULT_NUM_CTX = 8192
        def calculate_dynamic_num_ctx(p, min_ctx=8192): return min_ctx

    effective_num_ctx = int(cfg.get("num_ctx", calculate_dynamic_num_ctx(prompt, min_ctx=DEFAULT_NUM_CTX)))
    builder_options = {"temperature": 0.1, "top_p": 0.95, "num_predict": 4096, "num_ctx": effective_num_ctx}
    if cfg.get("num_thread"):
        builder_options["num_thread"] = int(cfg["num_thread"])
    else:
        try:
            cpus = os.cpu_count() or 4
            builder_options["num_thread"] = cpus // 2 if cpus >= 16 else (cpus if cpus > 4 else 4)
        except Exception:
            pass

    body = {"model": model, "prompt": prompt, "stream": False, "options": builder_options}
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})

    start_t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            patch_text = data.get("response", "")
            eval_count = data.get("eval_count") or max(len(patch_text.split()), 1)
            duration_ms = int((time.time() - start_t) * 1000)
            return {"patch": patch_text, "tokens": eval_count, "duration_ms": max(duration_ms, 1)}
    except Exception as e:
        raise RuntimeError(f"Falha na inferência do modelo local Ollama ({url}): {str(e)}")

def is_local_llm_recoverable_failure(err: Exception) -> bool:
    """Identifica se falha do Ollama é passível de re-roteamento: OOM, timeout, connection refused."""
    err_str = str(err).lower()
    patterns = ["out of memory", "oom", "cuda", "timeout", "timed out", "connection refused", "errno 111",
                "failed to connect", "unavailable", "cannot connect", "network is unreachable", "server disconnected"]
    return any(p in err_str for p in patterns) or isinstance(err, (TimeoutError, ConnectionRefusedError, urllib.error.URLError))

def call_omniroute_llm(
    instruction: str,
    target_file: str,
    existing_content: str,
    context_content: Optional[str] = None,
    error_feedback: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    project_id: Optional[str] = None
) -> Dict[str, Any]:
    """Executa inferência de fallback utilizando o gateway compatível com OpenAI do OmniRoute."""
    cfg = config or {}
    omni_cfg = {}
    try:
        import opencode_manager
        omni_cfg = opencode_manager.load_config()
    except Exception:
        pass

    base_url = (cfg.get("omniroute_url") or omni_cfg.get("omniroute_url") or os.environ.get("OMNIROUTE_URL") or "http://127.0.0.1:20128/v1").rstrip("/")
    endpoint = f"{base_url}/chat/completions" if base_url.endswith("/v1") else f"{base_url}/v1/chat/completions"

    raw_model = cfg.get("cloud_model") or cfg.get("omniroute_model") or omni_cfg.get("model") or os.environ.get("OMNIROUTE_MODEL") or "auto"
    clean_model = str(raw_model).strip()
    if clean_model.startswith("omniroute/"):
        clean_model = clean_model[len("omniroute/"):]
    clean_model = clean_model or "auto"

    api_key = cfg.get("omniroute_api_key") or omni_cfg.get("api_key") or os.environ.get("OMNIROUTE_API_KEY") or "omniroute-local"
    timeout = float(cfg.get("omniroute_timeout", 30.0))
    prompt = build_local_prompt(instruction, target_file, existing_content, context_content, error_feedback)

    payload = {
        "model": clean_model,
        "messages": [
            {"role": "system", "content": "Você é um engenheiro de software sênior de ponta focado em geração de código cirúrgico e seguro."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    start_t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"Falha na inferência via OmniRoute ({endpoint}): {str(e)}") from e

    choices = data.get("choices", [])
    if not choices:
        raise ValueError(f"Resposta inválida do OmniRoute ({endpoint}): choices ausente.")
    patch_text = choices[0].get("message", {}).get("content", "")
    if not patch_text or not patch_text.strip():
        raise ValueError("OmniRoute retornou conteúdo vazio para a geração de código.")

    tokens = data.get("usage", {}).get("completion_tokens") or max(len(patch_text.split()), 1)
    return {
        "patch": patch_text, "tokens": tokens, "duration_ms": max(int((time.time() - start_t) * 1000), 1),
        "model": data.get("model", clean_model), "provider": "omniroute"
    }
