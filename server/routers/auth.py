"""
server/routers/auth.py: Endpoints de autenticação do Agent Cockpit.
"""
import os
from fastapi import APIRouter, Request

try:
    from server.auth import auth_manager
except ImportError:
    from auth import auth_manager

router = APIRouter(tags=["auth"])


@router.get("/api/auth/status")
async def auth_status_endpoint(request: Request):
    """Endpoint público de verificação de status de autenticação."""
    req = auth_manager.is_auth_required()
    tok = auth_manager.extract_token_from_request(request) if req else None
    return {"auth_required": req, "authenticated": auth_manager.verify_token(tok) if req else True}


@router.get("/api/auth/verify")
async def auth_verify_endpoint(request: Request):
    """Endpoint público de validação de token (nunca retorna 401)."""
    if not auth_manager.is_auth_required():
        return {"valid": True, "auth_required": False}
    tok = auth_manager.extract_token_from_request(request)
    return {"valid": auth_manager.verify_token(tok), "auth_required": True}


@router.get("/api/auth/config")
async def auth_config_endpoint(request: Request):
    """Endpoint público de configuração de autenticação (sem expor o token)."""
    token_source = auth_manager.get_token_source()
    token_file = None
    if token_source == "file":
        token_file = os.path.join(auth_manager.token_storage_dir, "session_token.txt")
    return {
        "auth_required": auth_manager.is_auth_required(),
        "token_source": token_source,
        "token_file": token_file,
        "token_hint": (
            "Defina a variável de ambiente COCKPIT_AUTH_TOKEN com o token de acesso e reinicie o servidor, "
            "ou copie o conteúdo do arquivo states/session_token.txt gerado automaticamente."
        ),
    }
