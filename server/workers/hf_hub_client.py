"""
Hugging Face Hub Client para busca e integração de modelos GGUF com Ollama.
Permite consultar o repositório público do Hugging Face Hub aplicando filtros GGUF,
extraindo métricas (downloads, likes), autor, quantizações sugeridas e formatando a tag Ollama (hf.co/{id}).
"""

import json
import logging
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hf_hub_client")

QUANT_REGEX = re.compile(r'^(q\d+_[a-z0-9_]+|bf16|f16|f32)$', re.IGNORECASE)
DEFAULT_SUGGESTED_QUANTS = ["Q4_K_M", "Q8_0"]


class HFHubClient:
    """Cliente para a API de modelos do Hugging Face Hub."""

    def __init__(
        self,
        base_url: str = "https://huggingface.co/api/models",
        timeout: float = 5.0
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)

    def search_models(
        self,
        query: str = "",
        limit: int = 20,
        sort: str = "downloads",
        direction: int = -1
    ) -> List[Dict[str, Any]]:
        """
        Busca modelos no Hugging Face Hub filtrando exclusivamente por artefatos GGUF.
        
        Retorna lista de modelos estruturados com metadata relevante para o local worker.
        Em caso de timeout ou erro de rede, retorna lista vazia de forma resiliente.
        """
        params: Dict[str, Any] = {
            "filter": "gguf",
            "sort": sort,
            "direction": direction,
            "limit": max(1, min(int(limit), 100))
        }

        trimmed_query = query.strip() if query else ""
        if trimmed_query:
            params["search"] = trimmed_query

        query_string = urllib.parse.urlencode(params)
        request_url = f"{self.base_url}?{query_string}"

        req = urllib.request.Request(
            request_url,
            headers={
                "User-Agent": "AgentCockpit/1.0 (Local-Worker-Hub)",
                "Accept": "application/json"
            },
            method="GET"
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.getcode() != 200:
                    logger.warning(
                        "Hugging Face Hub API retornou status %s para URL %s",
                        resp.getcode(),
                        request_url
                    )
                    return []
                raw_bytes = resp.read()
                data = json.loads(raw_bytes.decode("utf-8"))
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            socket.timeout,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
            Exception
        ) as exc:
            logger.warning("Falha na consulta ao Hugging Face Hub (%s): %s", request_url, exc)
            return []

        if not isinstance(data, list):
            return []

        results: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            model_id = item.get("id") or item.get("modelId") or ""
            if not model_id:
                continue

            author = item.get("author")
            if not author:
                author = model_id.split("/")[0] if "/" in model_id else ""

            downloads = item.get("downloads", 0) or 0
            likes = item.get("likes", 0) or 0
            raw_tags = item.get("tags", [])
            tags = raw_tags if isinstance(raw_tags, list) else []

            # Extração de quantizações sugeridas a partir das tags
            suggested_quants: List[str] = []
            for tag in tags:
                if isinstance(tag, str) and QUANT_REGEX.match(tag):
                    upper_tag = tag.upper()
                    if upper_tag not in suggested_quants:
                        suggested_quants.append(upper_tag)

            if not suggested_quants:
                suggested_quants = list(DEFAULT_SUGGESTED_QUANTS)

            results.append({
                "id": model_id,
                "author": author,
                "downloads": int(downloads),
                "likes": int(likes),
                "tags": tags,
                "suggested_quants": suggested_quants,
                "ollama_tag": f"hf.co/{model_id}"
            })

        return results


def search_hf_models(
    query: str = "",
    limit: int = 20,
    timeout: float = 5.0
) -> List[Dict[str, Any]]:
    """Função utilitária para busca direta no Hugging Face Hub."""
    client = HFHubClient(timeout=timeout)
    return client.search_models(query=query, limit=limit)
