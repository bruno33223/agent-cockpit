"""
zeus_chat.py: Endpoints do Zeus Chat Engine, streaming SSE, processamento multimodal e transcrição STT.
Chief Architect: Function Calling tático, despacho de workers e telemetria de avatar.
"""

import uuid
import base64
from typing import Dict, Any, Optional, Set
from fastapi import APIRouter, HTTPException, Body, Request
from fastapi.responses import StreamingResponse, JSONResponse

from connection_manager import manager

try:
    import zeus_chat_engine
except ImportError:
    try:
        from server import zeus_chat_engine
    except ImportError:
        zeus_chat_engine = None

try:
    from workers.worker_queue import local_worker_queue
except ImportError:
    try:
        from server.workers.worker_queue import local_worker_queue
    except ImportError:
        local_worker_queue = None

try:
    from server.routers.orchestrator import notify_worker_task_completion
except ImportError:
    try:
        from routers.orchestrator import notify_worker_task_completion
    except ImportError:
        notify_worker_task_completion = None

router = APIRouter(tags=["zeus_chat"])
_notified_worker_tickets: Set[str] = set()


def _on_worker_queue_update(status: Dict[str, Any]):
    """Monitora conclusão de tarefas em segundo plano e emite notificação em PT-BR."""
    global _notified_worker_tickets
    for task in status.get("history", []):
        tid = task.get("ticket_id")
        if tid and tid not in _notified_worker_tickets and task.get("status") in ("completed", "error"):
            _notified_worker_tickets.add(tid)
            if notify_worker_task_completion:
                try:
                    notify_worker_task_completion(task)
                except Exception:
                    pass


if local_worker_queue:
    local_worker_queue.register_listener(_on_worker_queue_update)


@router.post("/api/zeus-chat/message")
async def post_zeus_chat_message_endpoint(req: Dict[str, Any] = Body(...)):
    if not zeus_chat_engine:
        raise HTTPException(status_code=500, detail="Módulo zeus_chat_engine não disponível.")

    session_id = req.get("session_id") or str(uuid.uuid4())
    message = req.get("message", "")
    model_id = req.get("model_id", "auto")
    backend = req.get("backend", "auto")
    images = req.get("images", [])
    system_prompt = req.get("system_prompt")

    if images and model_id != "auto":
        if not zeus_chat_engine.is_vision_model(model_id):
            return JSONResponse(status_code=400, content={"status": "error", "message": f"O modelo '{model_id}' não suporta visão multimodal."})

    event_generator = zeus_chat_engine.zeus_engine.stream_chat_sse(
        session_id=session_id, message=message, model_id=model_id, backend=backend,
        images=images, system_prompt=system_prompt, broadcast_callback=manager.broadcast_sync
    )

    return StreamingResponse(
        event_generator, media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )


@router.post("/api/zeus-chat/tool-dispatch")
def post_zeus_tool_dispatch_endpoint(payload: Dict[str, Any] = Body(...)):
    """Despacha uma ferramenta tática do Chief Architect diretamente via API."""
    tool = payload.get("tool") or payload.get("name")
    if not tool:
        raise HTTPException(status_code=400, detail="Parâmetro 'tool' é obrigatório.")
    params = payload.get("params") or payload.get("arguments") or {}
    project_id = payload.get("project_id")
    session_id = payload.get("session_id")
    try:
        from server.chat.tool_dispatcher import execute_zeus_tool
    except ImportError:
        from chat.tool_dispatcher import execute_zeus_tool
    return execute_zeus_tool(tool, params, project_id=project_id, session_id=session_id, broadcast_callback=manager.broadcast_sync)


@router.post("/api/audio/transcribe-and-optimize")
async def post_audio_transcribe_and_optimize_endpoint(request: Request):
    if not zeus_chat_engine:
        raise HTTPException(status_code=500, detail="Módulo zeus_chat_engine não disponível.")

    content_type = request.headers.get("content-type", "")
    audio_bytes, hint = b"", None

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="JSON inválido.")
        b64_str = body.get("audio_base64") or body.get("audio") or body.get("audio_data") or ""
        hint = body.get("hint") or body.get("text_hint") or body.get("prompt_hint")
        if b64_str:
            if "," in b64_str:
                b64_str = b64_str.split(",", 1)[1]
            try:
                audio_bytes = base64.b64decode(b64_str)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Erro ao decodificar áudio em base64: {str(e)}")
    elif "multipart/form-data" in content_type:
        raw_body = await request.body()
        audio_bytes, hint = zeus_chat_engine.zeus_engine.extract_audio_from_multipart(raw_body, content_type)
    else:
        audio_bytes = await request.body()
        hint = request.headers.get("x-audio-hint")

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Nenhum dado de áudio fornecido.")

    return zeus_chat_engine.zeus_engine.transcribe_and_optimize(audio_bytes=audio_bytes, hint=hint)


@router.post("/api/chat/validate-multimodal")
def post_chat_validate_multimodal_endpoint(payload: Dict[str, Any] = Body(...)):
    if not zeus_chat_engine:
        raise HTTPException(status_code=500, detail="Módulo zeus_chat_engine não disponível.")

    model_id = payload.get("model_id", "")
    image = payload.get("image") or payload.get("image_url") or payload.get("image_data")

    if not zeus_chat_engine.is_vision_model(model_id):
        return {"status": "ok", "supported": False, "message": "O modelo selecionado não suporta visão multimodal.", "model_id": model_id}

    image_info = None
    if image:
        val = zeus_chat_engine.validate_image_payload(image)
        if not val.get("valid"):
            return JSONResponse(status_code=400, content={"status": "error", "supported": True, "message": f"Payload de imagem inválido: {val.get('error')}", "model_id": model_id})
        image_info = val

    return {"status": "ok", "supported": True, "message": "Modelo compatível com visão multimodal.", "model_id": model_id, "image_info": image_info}


@router.get("/api/zeus-chat/session/{session_id}/history")
def get_zeus_chat_history_endpoint(session_id: str):
    if not zeus_chat_engine:
        raise HTTPException(status_code=500, detail="Módulo zeus_chat_engine não disponível.")
    history = zeus_chat_engine.zeus_engine.get_history(session_id)
    return {"status": "ok", "session_id": session_id, "history": history, "count": len(history)}


@router.delete("/api/zeus-chat/session/{session_id}")
def delete_zeus_chat_session_endpoint(session_id: str):
    if not zeus_chat_engine:
        raise HTTPException(status_code=500, detail="Módulo zeus_chat_engine não disponível.")
    success = zeus_chat_engine.zeus_engine.session_manager.delete_session(session_id)
    return {"status": "ok", "deleted": success, "session_id": session_id}
