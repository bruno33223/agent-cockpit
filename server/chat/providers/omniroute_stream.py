"""
server/chat/providers/omniroute_stream.py: Cliente SSE para gateway OmniRoute compatível com OpenAI.
"""

import json
import uuid
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional, Iterator

try:
    from server.chat.constants import AVAILABLE_TOOLS
    from server.chat.vision import is_vision_model
    from server.chat.providers.utils import parse_think_tags
except ImportError:
    from chat.constants import AVAILABLE_TOOLS
    from chat.vision import is_vision_model
    from chat.providers.utils import parse_think_tags


def stream_omniroute(
    omniroute_url: str,
    session_id: str,
    message: str,
    model_id: str = "auto",
    history: Optional[List[Dict[str, Any]]] = None,
    images: Optional[List[str]] = None,
    system_prompt: Optional[str] = None
) -> Iterator[Dict[str, Any]]:
    """Streaming de eventos a partir do endpoint compatível com OpenAI do OmniRoute."""
    url = f"{omniroute_url.rstrip('/')}/chat/completions"

    clean_model = (model_id or "auto").strip()
    if clean_model.startswith("omniroute/"):
        clean_model = clean_model[len("omniroute/"):]
    effective_model = clean_model if clean_model and clean_model != "auto" else "auto"

    messages: List[Dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        for msg in history:
            if msg.get("role") in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})

    user_content: Any = message
    if images and is_vision_model(effective_model):
        user_content = [{"type": "text", "text": message}]
        for img in images:
            user_content.append({"type": "image_url", "image_url": {"url": img}})

    if not messages or messages[-1]["role"] != "user":
        messages.append({"role": "user", "content": user_content})

    payload = {
        "model": effective_model,
        "messages": messages,
        "stream": True,
        "tools": AVAILABLE_TOOLS,
        "tool_choice": "auto"
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "User-Agent": "ZeusChatEngine/1.0"
    }
    try:
        try:
            from server.opencode_manager import load_config
        except ImportError:
            from opencode_manager import load_config
        cfg = load_config()
        api_key = cfg.get("api_key") or "omniroute-local"
        headers["Authorization"] = f"Bearer {api_key}"
    except Exception:
        headers["Authorization"] = "Bearer omniroute-local"

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers
    )

    in_think_tag = False

    try:
        resp_ctx = urllib.request.urlopen(req, timeout=30.0)
    except urllib.error.HTTPError as he:
        err_msg = f"HTTP Error {he.code}: {he.reason}"
        try:
            raw_body = he.read().decode("utf-8", errors="ignore")
            err_data = json.loads(raw_body)
            if isinstance(err_data, dict):
                err_obj = err_data.get("error")
                if isinstance(err_obj, dict):
                    msg = err_obj.get("message")
                elif isinstance(err_obj, str):
                    msg = err_obj
                else:
                    msg = err_data.get("message")
                if msg:
                    err_msg = f"OmniRoute: {msg}"
        except Exception:
            pass
        yield {"type": "error", "error": err_msg, "code": f"HTTP_{he.code}"}
        return
    except Exception as e:
        yield {"type": "error", "error": f"Falha de conexão com OmniRoute: {str(e)}", "code": "OMNIROUTE_CONN_ERROR"}
        return

    with resp_ctx as resp:
        for line in resp:
            line_str = line.decode("utf-8").strip() if isinstance(line, (bytes, bytearray)) else str(line).strip()
            if not line_str or not line_str.startswith("data:"):
                continue
            data_part = line_str[5:].strip()
            if data_part == "[DONE]":
                break

            try:
                chunk = json.loads(data_part)
            except Exception:
                continue

            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})

            # 1. Raciocínio (reasoning_content ou thinking)
            reasoning = delta.get("reasoning_content") or delta.get("thinking")
            if reasoning:
                yield {"type": "thinking", "text": reasoning}

            # 2. Chamadas de ferramentas (tool_calls)
            tool_calls = delta.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    fname = fn.get("name", "tool")
                    fargs = fn.get("arguments", "{}")
                    try:
                        parsed_args = json.loads(fargs) if isinstance(fargs, str) else fargs
                    except Exception:
                        parsed_args = {"raw": fargs}

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

            # 3. Conteúdo regular com parsing de tags <think>
            content = delta.get("content")
            if content:
                parts = parse_think_tags(content, in_think_tag)
                for p_type, p_text, in_think_tag in parts:
                    yield {"type": p_type, "text": p_text}
