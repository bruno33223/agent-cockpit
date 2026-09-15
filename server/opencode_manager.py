"""
opencode_manager.py: Gerenciador de integração para OpenCode e OmniRoute no Agent Cockpit.
Cuida da configuração do OmniRoute (endpoint, API key, modelos), detecção do binário
do OpenCode e geração determinística de opencode.json acoplado ao servidor MCP do Cockpit.
"""

import os
import sys
import json
import shutil
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_FILE = os.path.join(BASE_DIR, "cockpit-agent", "omniroute_config.json")
OPENCODE_JSON = os.path.join(BASE_DIR, "opencode.json")

DEFAULT_CONFIG = {
    "omniroute_url": "http://localhost:20128/v1",
    "api_key": "omniroute-local",
    "model": "auto",
    "enabled": True
}


def load_config() -> Dict[str, Any]:
    """Carrega as configurações salvas do OmniRoute/OpenCode ou retorna o padrão."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg = dict(DEFAULT_CONFIG)
                cfg.update(saved)
                return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    """Persiste as configurações no diretório cockpit-agent/ e atualiza opencode.json."""
    cfg = load_config()
    cfg.update(config_data)
    
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        
    sync_opencode_config(cfg)
    return cfg


def check_omniroute_health(base_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Testa se o OmniRoute está respondendo na URL especificada e lista os modelos disponíveis.
    """
    url = (base_url or load_config().get("omniroute_url", "http://localhost:20128/v1")).rstrip("/")
    models_endpoint = f"{url}/models"
    
    req = urllib.request.Request(
        models_endpoint,
        headers={
            "User-Agent": "Agent-Cockpit-Bridge/1.0",
            "Accept": "application/json"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models_list = []
            if isinstance(data, dict):
                raw_models = data.get("data", [])
                for m in raw_models:
                    if isinstance(m, dict) and "id" in m:
                        models_list.append(m["id"])
                    elif isinstance(m, str):
                        models_list.append(m)
            elif isinstance(data, list):
                for m in data:
                    if isinstance(m, dict) and "id" in m:
                        models_list.append(m["id"])
                    elif isinstance(m, str):
                        models_list.append(m)
            
            return {
                "online": True,
                "endpoint": url,
                "models": models_list,
                "message": f"Conectado ao OmniRoute com {len(models_list)} modelos disponíveis."
            }
    except Exception as e:
        return {
            "online": False,
            "endpoint": url,
            "models": [],
            "message": f"OmniRoute inacessível em {url}: {str(e)}"
        }


def detect_binaries() -> Dict[str, Any]:
    """Detecta se os binários do opencode e omniroute estão disponíveis no PATH ou NVM."""
    opencode_path = shutil.which("opencode")
    omniroute_path = shutil.which("omniroute")
    node_path = shutil.which("node")
    npm_path = shutil.which("npm")
    
    home = os.path.expanduser("~")
    nvm_bin = os.path.join(home, ".nvm", "versions", "node")
    if not opencode_path and os.path.isdir(nvm_bin):
        for version in os.listdir(nvm_bin):
            candidate = os.path.join(nvm_bin, version, "bin", "opencode")
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                opencode_path = candidate
                break
                
    if not omniroute_path and os.path.isdir(nvm_bin):
        for version in os.listdir(nvm_bin):
            candidate = os.path.join(nvm_bin, version, "bin", "omniroute")
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                omniroute_path = candidate
                break

    return {
        "opencode": {
            "installed": bool(opencode_path),
            "path": opencode_path
        },
        "omniroute": {
            "installed": bool(omniroute_path),
            "path": omniroute_path
        },
        "node": {
            "installed": bool(node_path),
            "path": node_path
        },
        "npm": {
            "installed": bool(npm_path),
            "path": npm_path
        }
    }


def sync_opencode_config(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Gera ou sincroniza o opencode.json na raiz do projeto apontando o provider
    para o OmniRoute e registrando o MCP Server do Agent Cockpit.
    """
    if cfg is None:
        cfg = load_config()
        
    omniroute_url = cfg.get("omniroute_url", "http://localhost:20128/v1").rstrip("/")
    api_key = cfg.get("api_key", "omniroute-local") or "omniroute-local"
    model = cfg.get("model", "auto") or "auto"
    
    python_executable = sys.executable
    mcp_server_script = os.path.join(BASE_DIR, "server", "mcp_server.py")
    
    opencode_structure = {
        "$schema": "https://opencode.ai/config.json",
        "model": f"omniroute/{model}",
        "provider": {
            "omniroute": {
                "npm": "@ai-sdk/openai",
                "name": "OmniRoute Gateway",
                "options": {
                    "baseURL": omniroute_url,
                    "apiKey": api_key
                },
                "models": {
                    model: {
                        "name": f"OmniRoute ({model})"
                    },
                    "auto": {
                        "name": "OmniRoute Auto Router"
                    }
                }
            }
        },
        "mcp": {
            "agent-cockpit": {
                "type": "local",
                "command": [python_executable, mcp_server_script],
                "enabled": True
            }
        }
    }
    
    try:
        with open(OPENCODE_JSON, "w", encoding="utf-8") as f:
            json.dump(opencode_structure, f, indent=2, ensure_ascii=False)
        return {"status": "success", "file": OPENCODE_JSON, "config": opencode_structure}
    except Exception as e:
        return {"status": "error", "message": str(e)}
