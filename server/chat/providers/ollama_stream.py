"""
server/chat/providers/ollama_stream.py: Cliente streaming para endpoint nativo Ollama local.
"""

import json
import uuid
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional, Iterator

try:
    from server.chat.constants import AVAILABLE_TOOLS
    from server.chat.providers.utils import parse_think_tags
except ImportError:
    from chat.constants import AVAILABLE_TOOLS
    from chat.providers.utils import parse_think_tags


def stream_ollama(
    ollama_url: str,
    session_id: str,
    message: str,
    model_id: str = "auto",
    history: Optional[List[Dict[str, Any]]] = None,
    system_prompt: Optional[str] = None
) -> Iterator[Dict[str, Any]]:
    """Streaming de eventos a partir do endpoint nativo /api/chat do Ollama."""
    url = f"{ollama_url.rstrip('/')}/api/chat"
    effective_model = model_id if model_id and model_id != "auto" else "qwen2.5-coder:7b"

    messages: List[Dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        for msg in history:
            if msg.get("role") in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})

    if not messages or messages[-1]["role"] != "user":
        messages.append({"role": "user", "content": message})

    payload = {
        "model": effective_model,
        "messages": messages,
        "stream": True,
        "tools": AVAILABLE_TOOLS
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    in_think_tag = False

    try:
        resp_ctx = urllib.request.urlopen(req, timeout=30.0)
    except Exception as e:
        yield {"type": "error", "error": f"Falha de conexão com Ollama: {str(e)}", "code": "OLLAMA_CONN_ERROR"}
        return

    with resp_ctx as resp:
        for line in resp:
            line_str = line.decode("utf-8").strip() if isinstance(line, (bytes, bytearray)) else str(line).strip()
            if not line_str:
                continue

            try:
                chunk = json.loads(line_str)
            except Exception:
                continue

            msg_chunk = chunk.get("message", {})
            thinking = msg_chunk.get("thinking")
            if thinking:
                yield {"type": "thinking", "text": thinking}

            tool_calls = msg_chunk.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    fname = fn.get("name", "tool")
                    fargs = fn.get("arguments", {})
                    parsed_args = json.loads(fargs) if isinstance(fargs, str) else (fargs if isinstance(fargs, dict) else {})

                    if "subagent" in fname.lower() or "spawn" in fname.lower():
                        slice_id = parsed_args.get("slice_id") or parsed_args.get("sliceId") or "slice-1"
                        role = parsed_args.get("role", "builder")
                        task = parsed_args.get("task") or parsed_args.get("title") or "Subagent Task"
                        title = parsed_args.get("title") or parsed_args.get("task") or f"Subagente [{slice_id}]"
                        target_files = parsed_args.get("target_files") or parsed_args.get("targetFiles") or []
                        if isinstance(target_files, str):
                            target_files = [target_files]
                        worktree_path = parsed_args.get("worktree_path") or parsed_args.get("worktreePath") or f".worktrees/{slice_id}"
                        yield {
                            "type": "subagent_spawn",
                            "id": str(tc.get("id", uuid.uuid4().hex[:8])),
                            "slice_id": slice_id,
                            "role": role,
                            "task": task,
                            "title": title,
                            "target_files": target_files,
                            "worktree_path": worktree_path,
                            "status": "running"
                        }
                    else:
                        yield {
                            "type": "tool_call",
                            "tool": fname,
                            "params": parsed_args,
                            "call_id": tc.get("id", str(uuid.uuid4()))
                        }

            content = msg_chunk.get("content")
            if content:
                parts = parse_think_tags(content, in_think_tag)
                for p_type, p_text, in_think_tag in parts:
                    yield {"type": p_type, "text": p_text}
