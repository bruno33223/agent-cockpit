"""
server/auth.py: Módulo de segurança e autenticação do Agent Cockpit.
Implementa validação de sessão local, tokens de segurança HTTP e WebSockets,
garantindo proteção para a API contra acessos não autorizados locais ou de rede.
Issue #38: [Security & Hardening] Autenticação local na API.
"""

import os
import sys
import hmac
import secrets
from typing import Optional, Dict, Any
from fastapi import Request, WebSocket
from fastapi.responses import JSONResponse


class AuthManager:
    """Gerencia tokens de sessão e autenticação do Cockpit."""

    PUBLIC_API_PATHS = {
        "/api/health",
        "/api/ping",
        "/api/auth/status",
        "/api/auth/verify",
        "/api/auth/config"
    }

    def __init__(self, token_storage_dir: Optional[str] = None):
        if token_storage_dir:
            self.token_storage_dir = os.path.abspath(token_storage_dir)
        else:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            self.token_storage_dir = os.path.join(base_dir, "states")

    def is_auth_required(self) -> bool:
        """Verifica se autenticação é requerida via ambiente ou configuração."""
        req = os.environ.get("COCKPIT_REQUIRE_AUTH", "").strip().lower()
        if req in ("0", "false", "no", "off"):
            return False
        if req in ("1", "true", "yes", "on"):
            return True
        if os.environ.get("COCKPIT_AUTH_TOKEN"):
            return True
        return False

    def get_token_source(self) -> Optional[str]:
        """Retorna a origem do token ativo: 'env', 'file' ou None (sem expor o valor)."""
        if os.environ.get("COCKPIT_AUTH_TOKEN", "").strip():
            return "env"
        token_file = os.path.join(self.token_storage_dir, "session_token.txt")
        if os.path.isfile(token_file):
            return "file"
        return None

    def get_or_create_session_token(self) -> str:
        """Retorna token de ambiente ou lê/cria arquivo states/session_token.txt."""
        env_token = os.environ.get("COCKPIT_AUTH_TOKEN", "").strip()
        if env_token:
            return env_token

        token_file = os.path.join(self.token_storage_dir, "session_token.txt")
        if os.path.isfile(token_file):
            try:
                with open(token_file, "r", encoding="utf-8") as f:
                    saved = f.read().strip()
                    if saved:
                        return saved
            except Exception:
                pass

        new_token = secrets.token_urlsafe(32)
        try:
            os.makedirs(self.token_storage_dir, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            mode = 0o600
            fd = os.open(token_file, flags, mode)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new_token + "\n")
        except Exception:
            # Fallback caso falhe escrita em disco
            pass

        return new_token

    def verify_token(self, token: Optional[str]) -> bool:
        """Valida token com tempo constante para evitar timing attacks."""
        if not self.is_auth_required():
            return True
        if not token or not isinstance(token, str):
            return False

        expected = self.get_or_create_session_token()
        return hmac.compare_digest(token.strip(), expected.strip())

    def extract_token_from_request(self, request: Request) -> Optional[str]:
        """Extrai token de headers X-Cockpit-Token, Authorization Bearer ou query param token."""
        # 1. Header X-Cockpit-Token
        header_token = request.headers.get("x-cockpit-token")
        if header_token and header_token.strip():
            return header_token.strip()

        # 2. Header Authorization: Bearer <token>
        auth_header = request.headers.get("authorization", "").strip()
        if auth_header.lower().startswith("bearer "):
            bearer_token = auth_header[7:].strip()
            if bearer_token:
                return bearer_token

        # 3. Query param token
        query_token = request.query_params.get("token")
        if query_token and query_token.strip():
            return query_token.strip()

        return None

    def is_public_path(self, path: str) -> bool:
        """Define se um endpoint é público (não requer token)."""
        clean_path = path.rstrip("/") if path != "/" else "/"
        if clean_path in self.PUBLIC_API_PATHS or path in self.PUBLIC_API_PATHS:
            return True
        # Rotas estáticas ou de frontend não são /api/
        if not clean_path.startswith("/api/"):
            return True
        return False


auth_manager = AuthManager()


async def auth_middleware(request: Request, call_next):
    """Middleware HTTP para validar requisições protegidas."""
    path = request.url.path
    if auth_manager.is_auth_required() and not auth_manager.is_public_path(path):
        token = auth_manager.extract_token_from_request(request)
        if not auth_manager.verify_token(token):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Unauthorized",
                    "error": "Acesso não autorizado: Token de sessão inválido ou ausente."
                }
            )
    return await call_next(request)


async def verify_ws_auth(websocket: WebSocket) -> bool:
    """Verifica autenticação na conexão WebSocket /ws. Fecha com código 1008 se não autorizado."""
    if not auth_manager.is_auth_required():
        return True

    # Busca em query params ?token=...
    token = websocket.query_params.get("token")

    # Fallback para headers se suportado pelo cliente
    if not token:
        token = websocket.headers.get("x-cockpit-token")
    if not token:
        auth_hdr = websocket.headers.get("authorization", "").strip()
        if auth_hdr.lower().startswith("bearer "):
            token = auth_hdr[7:].strip()

    if auth_manager.verify_token(token):
        return True

    await websocket.accept()
    await websocket.close(code=1008, reason="Unauthorized")
    return False
