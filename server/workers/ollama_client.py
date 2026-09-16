"""
OllamaClient: Cliente HTTP resiliente para Ollama com context window dinâmico e num_ctx expandido.
Previne truncamento silencioso em prompts extensos e arquivos de código completos.
"""

import json
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional, Callable

DEFAULT_NUM_CTX = 8192
MAX_NUM_CTX = 32768


def calculate_dynamic_num_ctx(
    prompt_or_text: str,
    min_ctx: int = DEFAULT_NUM_CTX,
    max_ctx: int = MAX_NUM_CTX,
    output_buffer_tokens: int = 4096
) -> int:
    """
    Calcula dinamicamente a janela de contexto necessária para acomodar o prompt e o buffer de resposta.
    Garante no mínimo min_ctx (8192 por padrão) e escala suavemente até max_ctx para prompts grandes.
    """
    if not prompt_or_text:
        return min_ctx

    # Estimativa conservadora de tokens para código (aprox. 3 caracteres por token em média)
    estimated_prompt_tokens = int(len(prompt_or_text) / 3.0)
    needed_tokens = estimated_prompt_tokens + output_buffer_tokens

    if needed_tokens <= min_ctx:
        return min_ctx

    step = 2048
    scaled = ((needed_tokens + step - 1) // step) * step
    return min(scaled, max_ctx)


class OllamaClient:
    """
    Cliente para integração com a API do Ollama (/api/generate, /api/tags, /api/pull).
    Configura por padrão context window de 8192 e preserva parâmetros customizados.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 120.0,
        default_num_ctx: int = DEFAULT_NUM_CTX
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.default_num_ctx = default_num_ctx

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Executa requisição HTTP usando urllib com timeout configurável."""
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        req_timeout = timeout or self.timeout

        with urllib.request.urlopen(req, timeout=req_timeout) as resp:
            body = resp.read().decode("utf-8")
            if body:
                return json.loads(body)
            return {}

    def healthcheck(self) -> bool:
        """Retorna True se o servidor Ollama estiver respondendo."""
        try:
            self._request("/api/tags", method="GET", timeout=5.0)
            return True
        except Exception:
            return False

    def generate(
        self,
        prompt: str,
        model: str = "qwen2.5-coder:7b",
        stream: bool = False,
        options: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Envia requisição para /api/generate com num_ctx seguro (8192 por padrão ou dinamicamente escalado).
        Se o chamador especificar 'num_ctx' em options, o valor customizado é estritamente respeitado.
        """
        opts = dict(options) if options else {}

        if "num_ctx" not in opts:
            opts["num_ctx"] = calculate_dynamic_num_ctx(prompt, min_ctx=self.default_num_ctx)
        else:
            opts["num_ctx"] = int(opts["num_ctx"])

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
            "options": opts
        }

        return self._request("/api/generate", method="POST", payload=payload, timeout=timeout)
