"""
server/chat/vision.py: Utilitários multimodais e validação de imagens em RAM.
"""

import re
import base64
from typing import Dict, Any, Optional

VISION_MODEL_PATTERNS = [
    r"gpt-4o",
    r"gpt-4-turbo",
    r"gpt-4-vision",
    r"chatgpt-4o",
    r"o1",
    r"o3",
    r"claude-3",
    r"claude-3\.5",
    r"claude-3-5",
    r"claude-3\.7",
    r"claude-3-7",
    r"claude-.*",
    r"gemini",
    r"gemini-.*",
    r"qwen.*vl",
    r"llava",
    r"bakllava",
    r"moondream",
    r"pixtral",
    r"minicpm-v",
    r"phi-3.*vision",
    r"vision",
    r"auto"
]

VISION_REGEX = re.compile("|".join(VISION_MODEL_PATTERNS), re.IGNORECASE)


def is_vision_model(model_id: Optional[str]) -> bool:
    """Verifica se o identificador do modelo possui capacidade de visão multimodal."""
    if not model_id or not isinstance(model_id, str):
        return False
    clean_id = model_id.strip().lower()
    return bool(VISION_REGEX.search(clean_id))


def validate_image_payload(image_data: str) -> Dict[str, Any]:
    """
    Valida um payload de imagem fornecido como Data URL ou string Base64.
    Decodifica em RAM e valida formato e integridade básica de bytes.
    """
    if not image_data or not isinstance(image_data, str):
        return {"valid": False, "error": "Payload de imagem vazio ou tipo inválido."}

    raw_b64 = image_data.strip()
    detected_mime = "image/png"

    if raw_b64.startswith("data:"):
        match = re.match(r"^data:(image\/[a-zA-Z0-9\+\-\.]+);base64,(.+)$", raw_b64, re.DOTALL)
        if not match:
            return {"valid": False, "error": "Formato de Data URL inválido para imagem."}
        detected_mime = match.group(1).lower()
        raw_b64 = match.group(2).strip()

    try:
        decoded = base64.b64decode(raw_b64, validate=True)
    except Exception as e:
        return {"valid": False, "error": f"Falha ao decodificar Base64 da imagem: {str(e)}"}

    if len(decoded) == 0:
        return {"valid": False, "error": "A imagem decodificada está vazia (0 bytes)."}

    img_format = "unknown"
    if decoded.startswith(b"\x89PNG\r\n\x1a\n"):
        img_format = "png"
    elif decoded.startswith(b"\xff\xd8\xff"):
        img_format = "jpeg"
    elif decoded.startswith(b"GIF87a") or decoded.startswith(b"GIF89a"):
        img_format = "gif"
    elif len(decoded) >= 12 and decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP":
        img_format = "webp"
    elif b"<svg" in decoded[:256].lower():
        img_format = "svg"
    else:
        if "image/" in detected_mime:
            img_format = detected_mime.split("/")[-1]
        else:
            return {"valid": False, "error": "Assinatura binária de imagem não reconhecida."}

    return {
        "valid": True,
        "format": img_format,
        "size_bytes": len(decoded),
        "mime_type": detected_mime or f"image/{img_format}"
    }
