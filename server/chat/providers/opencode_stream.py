"""
server/chat/providers/opencode_stream.py: Execução de subprocesso OpenCode CLI e streaming SSE/NDJSON.
"""

import os
import json
import uuid
import base64
import shutil
import subprocess
from typing import Dict, List, Any, Optional, Iterator


def stream_opencode(
    session_id: str,
    message: str,
    model_id: str = "auto",
    images: Optional[List[str]] = None,
    system_prompt: Optional[str] = None
) -> Iterator[Dict[str, Any]]:
    """
    Executa inferência real através do OpenCode CLI com streaming de eventos NDJSON.
    Transmite eventos reais de reasoning (thinking), text (content), tool_use e step_finish.
    Emite erro transparente caso o processo falhe, sem inventar texto falso.
    """
    try:
        from server.opencode_manager import detect_binaries
        bins = detect_binaries()
        opencode_bin = bins.get("opencode", {}).get("path")
    except Exception:
        opencode_bin = shutil.which("opencode")

    resolved_bin = None
    if opencode_bin:
        if os.path.isfile(opencode_bin):
            resolved_bin = opencode_bin
        elif shutil.which(opencode_bin):
            resolved_bin = shutil.which(opencode_bin)

    if not resolved_bin:
        yield {
            "type": "error",
            "error": "Binário do OpenCode não encontrado. Certifique-se de que o OpenCode está instalado no ambiente.",
            "code": "OPENCODE_BIN_NOT_FOUND"
        }
        return

    cmd = [resolved_bin, "run"]
    if model_id and model_id != "auto":
        cmd.extend(["-m", model_id])
    cmd.extend(["--format", "json", "--thinking"])

    temp_files: List[str] = []
    if images and isinstance(images, list):
        for i, img_b64 in enumerate(images):
            try:
                clean_b64 = img_b64
                if "," in clean_b64:
                    clean_b64 = clean_b64.split(",", 1)[1]
                decoded = base64.b64decode(clean_b64)
                temp_path = f"/tmp/zeus_img_{uuid.uuid4().hex[:8]}_{i}.png"
                with open(temp_path, "wb") as f:
                    f.write(decoded)
                temp_files.append(temp_path)
                cmd.extend(["--file", temp_path])
            except Exception as e:
                yield {
                    "type": "error",
                    "error": f"Erro ao processar anexo de imagem: {str(e)}",
                    "code": "IMAGE_ATTACHMENT_ERROR"
                }
                return

    final_prompt = message
    if system_prompt and system_prompt.strip():
        final_prompt = f"{system_prompt.strip()}\n\n{message}"

    cmd.append(final_prompt)

    had_error = False
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=os.environ.copy()
        )

        if proc.stdout:
            stdout_iter = proc.stdout if isinstance(proc.stdout, (list, tuple)) else iter(proc.stdout.readline, "")
            for raw_line in stdout_iter:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ev_type = data.get("type")
                part = data.get("part", {})

                if ev_type == "reasoning":
                    text = part.get("text", "")
                    if text:
                        yield {"type": "thinking", "text": text}

                elif ev_type == "text":
                    text = part.get("text", "")
                    if text:
                        yield {"type": "content", "text": text}

                elif ev_type in ("tool_use", "tool_call"):
                    state = part.get("state", {}) if isinstance(part.get("state"), dict) else {}
                    tool_name = (
                        part.get("tool")
                        or part.get("name")
                        or data.get("tool")
                        or state.get("title")
                        or "tool"
                    )
                    tool_input = (
                        state.get("input")
                        or part.get("arguments")
                        or data.get("params")
                        or {}
                    )
                    command_detail = state.get("title") or ""
                    if not command_detail and isinstance(tool_input, dict):
                        command_detail = (
                            tool_input.get("command")
                            or tool_input.get("path")
                            or tool_input.get("pattern")
                            or tool_input.get("query")
                            or ""
                        )

                    tool_output = state.get("output") or state.get("metadata", {}).get("output") or ""
                    tool_status = state.get("status") or "completed"

                    if tool_name in ("task", "subagent") or "subagent" in str(tool_name).lower():
                        slice_id = (
                            tool_input.get("slice_id")
                            or tool_input.get("sliceId")
                            or (f"task-{part.get('callID')[:6]}" if part.get("callID") else "slice-1")
                        )
                        role = tool_input.get("role") or tool_input.get("agent") or "builder"
                        task = tool_input.get("task") or state.get("title") or tool_input.get("description") or f"Subagente {tool_name}"
                        title = state.get("title") or task or f"Subagente [{slice_id}]"
                        target_files = tool_input.get("target_files") or tool_input.get("targetFiles") or []
                        if isinstance(target_files, str):
                            target_files = [target_files]
                        worktree_path = tool_input.get("worktree_path") or tool_input.get("worktreePath") or f".worktrees/{slice_id}"
                        yield {
                            "type": "subagent_spawn",
                            "id": part.get("callID") or part.get("id") or f"subagent-{uuid.uuid4().hex[:6]}",
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
                            "tool": tool_name,
                            "params": tool_input,
                            "command": command_detail,
                            "output": tool_output,
                            "status": tool_status,
                            "call_id": part.get("callID") or part.get("id") or data.get("call_id")
                        }

                elif ev_type == "step_finish":
                    tokens = part.get("tokens", {})
                    yield {
                        "type": "step_finish",
                        "tokens": tokens,
                        "cost": part.get("cost", 0),
                        "backend": "opencode"
                    }

                elif ev_type == "error":
                    had_error = True
                    err_obj = data.get("error", {})
                    err_msg = err_obj.get("message") or str(err_obj)
                    yield {
                        "type": "error",
                        "error": f"OpenCode retornou erro: {err_msg}",
                        "code": "OPENCODE_STREAM_ERROR"
                    }

        proc.wait()

        if proc.returncode != 0 and not had_error:
            stderr_text = proc.stderr.read().strip() if proc.stderr else ""
            err_msg = stderr_text or f"Processo OpenCode finalizou com erro (código: {proc.returncode})"
            yield {
                "type": "error",
                "error": err_msg,
                "code": "OPENCODE_PROCESS_ERROR"
            }

    except Exception as e:
        yield {
            "type": "error",
            "error": f"Falha na execução do OpenCode: {str(e)}",
            "code": "OPENCODE_EXEC_FAILED"
        }
    finally:
        for tmp in temp_files:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
