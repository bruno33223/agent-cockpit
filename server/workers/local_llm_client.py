"""
LocalLLMClient: Cliente para integração com servidores locais Ollama/OpenAI compatíveis.
"""

import json
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional


class LocalLLMClient:
    RECOMMENDED_MODELS = [
        "qwen2.5-coder:7b",
        "qwen2.5-coder:1.5b",
        "deepseek-coder:6.7b",
        "codellama:7b",
        "llama3.2:3b",
    ]

    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executa requisição HTTP utilizando a stdlib urllib de forma segura e com timeout.
        """
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = resp.read().decode("utf-8")
            if body:
                return json.loads(body)
            return {}

    def healthcheck(self) -> bool:
        """
        Verifica se o servidor Ollama local está ativo e respondendo.
        Retorna True se online, False caso contrário (sem disparar exceções).
        """
        try:
            self._request("/api/tags", method="GET")
            return True
        except Exception:
            return False

    def list_models(self) -> Dict[str, Any]:
        """
        Lista os modelos instalados no Ollama (/api/tags) juntamente com modelos recomendados.
        Em caso de erro de conexão, aplica fallback gracioso.
        """
        try:
            data = self._request("/api/tags", method="GET")
            installed = [m.get("name", "") for m in data.get("models", []) if "name" in m]
            return {
                "online": True,
                "installed": installed,
                "recommended": list(self.RECOMMENDED_MODELS)
            }
        except Exception:
            return {
                "online": False,
                "installed": [],
                "recommended": list(self.RECOMMENDED_MODELS)
            }

    def pull_model(self, model_name: str, stream: bool = False) -> Dict[str, Any]:
        """
        Inicia o download de um modelo via endpoint /api/pull.
        """
        payload = {"name": model_name, "stream": stream}
        try:
            return self._request("/api/pull", method="POST", payload=payload)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str = "qwen2.5-coder:7b",
        temperature: float = 0.2,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Executa inferência utilizando o endpoint compatível com OpenAI (/v1/chat/completions).
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        return self._request("/v1/chat/completions", method="POST", payload=payload)

    def format_patch_prompt(self, file_path: str, file_content: str, instructions: str) -> str:
        """
        Formata o prompt instruindo o modelo a produzir saídas no formato SEARCH/REPLACE.
        """
        return f"""Você é um agente especialista em engenharia de software e geração de patches seguros.
Sua tarefa é modificar o arquivo: {file_path}

INSTRUÇÕES DE MODIFICAÇÃO:
{instructions}

CONTEÚDO ATUAL DO ARQUIVO:
```{file_path}
{file_content}
```

REGRAS ESTRITAS DE FORMATAÇÃO:
1. Responda ESTRITAMENTE com um ou mais blocos SEARCH/REPLACE.
2. Cada bloco DEVE seguir o padrão exato:
<<<<<<< SEARCH
[código original a ser substituído]
=======
[novo código substituto]
>>>>>>>
3. Para criar um arquivo novo ou sobrescrever por completo, utilize:
<<<<<<< SEARCH
=======
[conteúdo completo do novo arquivo]
>>>>>>>
4. O trecho SEARCH deve corresponder perfeitamente ao texto original do arquivo.
"""

    format_search_replace_prompt = format_patch_prompt
