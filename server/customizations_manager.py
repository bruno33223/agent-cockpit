"""
customizations_manager.py: Gerenciador de customizações do Agent Cockpit.
Cuida da persistência determinística de servidores MCP (mcp/) e Skills (skills/)
no diretório canônico do usuário (~/.config/agent-cockpit/customizations ou COCKPIT_CUSTOMIZATIONS_DIR),
além de sincronização segura com opencode.json.
"""

import os
import sys
import json
import re
import shutil
from typing import Dict, Any, Optional, List


def _get_default_customizations_dir() -> str:
    """Retorna o diretório canônico padrão de customizações de acordo com o SO."""
    env_dir = os.environ.get("COCKPIT_CUSTOMIZATIONS_DIR")
    if env_dir:
        return os.path.abspath(env_dir)

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return os.path.join(appdata, "AgentCockpit", "customizations")
        return os.path.expanduser("~/AppData/Roaming/AgentCockpit/customizations")

    return os.path.expanduser("~/.config/agent-cockpit/customizations")


def _sanitize_identifier(name: str) -> str:
    """Gera um identificador seguro para arquivos e diretórios sem path traversal."""
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "-", name.strip().lower())
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")
    return sanitized or "custom-item"


def _parse_skill_markdown(content: str) -> Dict[str, Any]:
    """Faz o parse de um arquivo SKILL.md contendo YAML frontmatter e corpo markdown."""
    metadata: Dict[str, Any] = {
        "name": "",
        "description": "",
        "enabled": True
    }
    instructions = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            raw_frontmatter = parts[1].strip()
            instructions = parts[2].strip()

            for line in raw_frontmatter.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if val.lower() == "true":
                        metadata[key] = True
                    elif val.lower() == "false":
                        metadata[key] = False
                    else:
                        metadata[key] = val

    metadata["instructions"] = instructions
    return metadata


def _serialize_skill_markdown(metadata: Dict[str, Any], instructions: str) -> str:
    """Serializa os metadados e instruções em formato SKILL.md com YAML frontmatter."""
    name = metadata.get("name", "")
    description = metadata.get("description", "")
    enabled = "true" if metadata.get("enabled", True) else "false"

    frontmatter = f"---\nname: {name}\ndescription: {description}\nenabled: {enabled}\n---\n\n"
    return frontmatter + instructions.strip() + "\n"


class CustomizationsManager:
    """Gerenciador de customizações locais (MCPs e Skills) com auto-sync OpenCode."""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self.base_dir = os.path.abspath(base_dir)
        else:
            self.base_dir = _get_default_customizations_dir()

        self.mcp_dir = os.path.join(self.base_dir, "mcp")
        self.skills_dir = os.path.join(self.base_dir, "skills")

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Garante a existência determinística dos diretórios base, mcp/ e skills/."""
        os.makedirs(self.mcp_dir, exist_ok=True)
        os.makedirs(self.skills_dir, exist_ok=True)

    # -------------------------------------------------------------------------
    # MCP SERVERS CRUD
    # -------------------------------------------------------------------------

    def create_mcp(self, mcp_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cria um novo servidor MCP.
        Valida tipos (stdio, sse, http) e campos obrigatórios.
        """
        name = mcp_data.get("name") or mcp_data.get("id")
        if not name or not str(name).strip():
            raise ValueError("O campo 'name' ou 'id' é obrigatório para servidores MCP.")

        mcp_type = mcp_data.get("type")
        if mcp_type not in ("stdio", "sse", "http"):
            raise ValueError(f"Tipo de MCP inválido: '{mcp_type}'. Permitidos: 'stdio', 'sse', 'http'.")

        mcp_id = mcp_data.get("id") or _sanitize_identifier(name)
        mcp_id = _sanitize_identifier(mcp_id)

        record: Dict[str, Any] = {
            "id": mcp_id,
            "name": str(name).strip(),
            "type": mcp_type,
            "description": mcp_data.get("description", ""),
            "enabled": bool(mcp_data.get("enabled", True))
        }

        if mcp_type == "stdio":
            command = mcp_data.get("command")
            if not command:
                raise ValueError("O campo 'command' é obrigatório para servidores MCP do tipo stdio.")
            record["command"] = command
            record["args"] = list(mcp_data.get("args") or [])
            record["env"] = dict(mcp_data.get("env") or {})
        else:  # sse ou http
            url = mcp_data.get("url")
            if not url or not str(url).strip():
                raise ValueError(f"O campo 'url' é obrigatório para servidores MCP do tipo {mcp_type}.")
            record["url"] = str(url).strip()
            record["headers"] = dict(mcp_data.get("headers") or {})

        target_file = os.path.join(self.mcp_dir, f"{mcp_id}.json")
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)

        return record

    def get_mcp(self, mcp_id: str) -> Optional[Dict[str, Any]]:
        """Retorna os dados de um servidor MCP por id, ou None se não existir."""
        safe_id = _sanitize_identifier(mcp_id)
        target_file = os.path.join(self.mcp_dir, f"{safe_id}.json")
        if not os.path.isfile(target_file):
            return None

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def list_mcps(self) -> List[Dict[str, Any]]:
        """Lista todos os servidores MCP configurados."""
        results: List[Dict[str, Any]] = []
        if not os.path.isdir(self.mcp_dir):
            return results

        for fname in sorted(os.listdir(self.mcp_dir)):
            if fname.endswith(".json"):
                fpath = os.path.join(self.mcp_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            results.append(data)
                except Exception:
                    continue
        return results

    def update_mcp(self, mcp_id: str, mcp_data: Dict[str, Any]) -> Dict[str, Any]:
        """Atualiza os dados de um servidor MCP existente."""
        current = self.get_mcp(mcp_id)
        if not current:
            raise KeyError(f"Servidor MCP '{mcp_id}' não encontrado.")

        # Preserva ID original
        target_id = current["id"]

        # Atualiza campos válidos
        if "name" in mcp_data and mcp_data["name"]:
            current["name"] = str(mcp_data["name"]).strip()
        if "description" in mcp_data:
            current["description"] = mcp_data["description"]
        if "enabled" in mcp_data:
            current["enabled"] = bool(mcp_data["enabled"])

        new_type = mcp_data.get("type", current.get("type"))
        if new_type not in ("stdio", "sse", "http"):
            raise ValueError(f"Tipo de MCP inválido: '{new_type}'.")
        current["type"] = new_type

        if new_type == "stdio":
            if "command" in mcp_data:
                if not mcp_data["command"]:
                    raise ValueError("O campo 'command' não pode ser vazio.")
                current["command"] = mcp_data["command"]
            if "args" in mcp_data:
                current["args"] = list(mcp_data["args"])
            if "env" in mcp_data:
                current["env"] = dict(mcp_data["env"])
            current.pop("url", None)
            current.pop("headers", None)
        else:
            if "url" in mcp_data:
                if not mcp_data["url"]:
                    raise ValueError(f"O campo 'url' é obrigatório para {new_type}.")
                current["url"] = str(mcp_data["url"]).strip()
            if "headers" in mcp_data:
                current["headers"] = dict(mcp_data["headers"])
            current.pop("command", None)
            current.pop("args", None)
            current.pop("env", None)

        target_file = os.path.join(self.mcp_dir, f"{target_id}.json")
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)

        return current

    def delete_mcp(self, mcp_id: str) -> bool:
        """Exclui um servidor MCP. Retorna True se deletou, False caso contrário."""
        safe_id = _sanitize_identifier(mcp_id)
        target_file = os.path.join(self.mcp_dir, f"{safe_id}.json")
        if os.path.isfile(target_file):
            try:
                os.remove(target_file)
                return True
            except Exception:
                return False
        return False

    def toggle_mcp(self, mcp_id: str, enabled: Optional[bool] = None) -> Dict[str, Any]:
        """Altera o status ativo/inativo de um servidor MCP."""
        current = self.get_mcp(mcp_id)
        if not current:
            raise KeyError(f"Servidor MCP '{mcp_id}' não encontrado.")

        new_status = not current.get("enabled", True) if enabled is None else bool(enabled)
        current["enabled"] = new_status

        safe_id = current["id"]
        target_file = os.path.join(self.mcp_dir, f"{safe_id}.json")
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)

        return current

    # -------------------------------------------------------------------------
    # SKILLS CRUD
    # -------------------------------------------------------------------------

    def create_skill(self, skill_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cria uma nova Skill com pasta dedicada e SKILL.md.
        """
        name = skill_data.get("name")
        if not name or not str(name).strip():
            raise ValueError("O campo 'name' é obrigatório para a Skill.")

        skill_name = _sanitize_identifier(name)
        description = skill_data.get("description", "")
        instructions = skill_data.get("instructions") or skill_data.get("content") or ""
        enabled = bool(skill_data.get("enabled", True))

        skill_dir = os.path.join(self.skills_dir, skill_name)
        os.makedirs(skill_dir, exist_ok=True)

        meta = {
            "name": skill_name,
            "description": description,
            "enabled": enabled
        }
        content = _serialize_skill_markdown(meta, instructions)

        skill_file = os.path.join(skill_dir, "SKILL.md")
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "name": skill_name,
            "description": description,
            "enabled": enabled,
            "instructions": instructions,
            "path": skill_dir
        }

    def get_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Retorna os dados e instruções de uma Skill a partir do SKILL.md."""
        safe_name = _sanitize_identifier(skill_name)
        skill_dir = os.path.join(self.skills_dir, safe_name)
        skill_file = os.path.join(skill_dir, "SKILL.md")

        if not os.path.isfile(skill_file):
            return None

        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                raw_text = f.read()
            parsed = _parse_skill_markdown(raw_text)
            parsed["name"] = parsed.get("name") or safe_name
            parsed["path"] = skill_dir
            return parsed
        except Exception:
            return None

    def list_skills(self) -> List[Dict[str, Any]]:
        """Lista todas as Skills disponíveis no diretório skills/."""
        results: List[Dict[str, Any]] = []
        if not os.path.isdir(self.skills_dir):
            return results

        for item in sorted(os.listdir(self.skills_dir)):
            item_path = os.path.join(self.skills_dir, item)
            if os.path.isdir(item_path):
                skill = self.get_skill(item)
                if skill:
                    results.append(skill)
        return results

    def update_skill(self, skill_name: str, skill_data: Dict[str, Any]) -> Dict[str, Any]:
        """Atualiza metadados ou instruções de uma Skill existente."""
        current = self.get_skill(skill_name)
        if not current:
            raise KeyError(f"Skill '{skill_name}' não encontrada.")

        safe_name = current["name"]
        skill_dir = os.path.join(self.skills_dir, safe_name)
        skill_file = os.path.join(skill_dir, "SKILL.md")

        if "description" in skill_data:
            current["description"] = skill_data["description"]
        if "enabled" in skill_data:
            current["enabled"] = bool(skill_data["enabled"])

        new_instructions = skill_data.get("instructions")
        if new_instructions is None:
            new_instructions = skill_data.get("content", current.get("instructions", ""))
        current["instructions"] = new_instructions

        serialized = _serialize_skill_markdown(current, new_instructions)
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(serialized)

        return current

    def delete_skill(self, skill_name: str) -> bool:
        """Remove o diretório de uma Skill e seu SKILL.md."""
        safe_name = _sanitize_identifier(skill_name)
        skill_dir = os.path.join(self.skills_dir, safe_name)
        if os.path.isdir(skill_dir):
            try:
                shutil.rmtree(skill_dir)
                return True
            except Exception:
                return False
        return False

    def toggle_skill(self, skill_name: str, enabled: Optional[bool] = None) -> Dict[str, Any]:
        """Altera o status ativo/inativo de uma Skill."""
        current = self.get_skill(skill_name)
        if not current:
            raise KeyError(f"Skill '{skill_name}' não encontrada.")

        new_status = not current.get("enabled", True) if enabled is None else bool(enabled)
        return self.update_skill(skill_name, {"enabled": new_status})

    # -------------------------------------------------------------------------
    # OPENCODE SYNC
    # -------------------------------------------------------------------------

    def sync_with_opencode(self, opencode_config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Sincroniza os servidores MCP ativos no arquivo opencode.json.
        Preserva conectores, providers e configurações existentes, atualizando
        apenas a chave 'mcp' com os servidores gerenciados.
        """
        if not opencode_config_path:
            base_project = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            opencode_config_path = os.path.join(base_project, "opencode.json")

        opencode_data: Dict[str, Any] = {}
        if os.path.isfile(opencode_config_path):
            try:
                with open(opencode_config_path, "r", encoding="utf-8") as f:
                    opencode_data = json.load(f)
            except Exception:
                opencode_data = {}

        if "$schema" not in opencode_data:
            opencode_data["$schema"] = "https://opencode.ai/config.json"

        if "mcp" not in opencode_data or not isinstance(opencode_data["mcp"], dict):
            opencode_data["mcp"] = {}

        managed_mcps = self.list_mcps()

        for mcp in managed_mcps:
            mcp_name = mcp.get("name")
            if not mcp_name:
                continue

            if mcp.get("enabled", True):
                mcp_type = mcp.get("type", "stdio")
                if mcp_type == "stdio":
                    cmd = mcp.get("command")
                    args = mcp.get("args") or []
                    if isinstance(cmd, list):
                        full_command = cmd + args
                    else:
                        full_command = [cmd] + args

                    entry: Dict[str, Any] = {
                        "type": "local",
                        "command": full_command
                    }
                    if mcp.get("env"):
                        entry["environment"] = dict(mcp["env"])
                    opencode_data["mcp"][mcp_name] = entry

                elif mcp_type in ("sse", "http"):
                    entry = {
                        "type": "remote",
                        "url": mcp.get("url")
                    }
                    if mcp.get("headers"):
                        entry["headers"] = dict(mcp["headers"])
                    opencode_data["mcp"][mcp_name] = entry
            else:
                # Se estiver desabilitado e constar no opencode.json, remove
                if mcp_name in opencode_data["mcp"]:
                    del opencode_data["mcp"][mcp_name]

        try:
            with open(opencode_config_path, "w", encoding="utf-8") as f:
                json.dump(opencode_data, f, indent=2, ensure_ascii=False)
            return {
                "status": "success",
                "file": opencode_config_path,
                "config": opencode_data
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }

