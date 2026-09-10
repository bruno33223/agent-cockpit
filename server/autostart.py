"""
Módulo de Gerenciamento de Inicialização com o Sistema Operacional (Autostart)
Suporte nativo a Linux (especificação FreeDesktop / XDG Autostart) de forma limpa e sem gambiarras.
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Dict, Any

AUTOSTART_DIR = Path.home() / ".config" / "autostart"
DESKTOP_ENTRY_NAME = "agent-cockpit.desktop"
AUTOSTART_FILE = AUTOSTART_DIR / DESKTOP_ENTRY_NAME

APPLICATIONS_DIR = Path.home() / ".local" / "share" / "applications"
APP_DESKTOP_FILE = APPLICATIONS_DIR / DESKTOP_ENTRY_NAME

def get_cockpit_paths():
    """Retorna os caminhos absolutos do interpretador Python e do script run_cockpit.py."""
    base_dir = Path(__file__).resolve().parent.parent
    run_script = base_dir / "run_cockpit.py"
    python_exec = Path(sys.executable).resolve()
    return base_dir, run_script, python_exec

def generate_desktop_entry_content() -> str:
    """Gera o conteúdo padrão de um arquivo .desktop de acordo com a especificação FreeDesktop."""
    base_dir, run_script, python_exec = get_cockpit_paths()
    return f"""[Desktop Entry]
Type=Application
Version=1.0
Name=Agent Cockpit
Comment=Painel de Telemetria e Orquestração Multiagente
Exec={python_exec} {run_script}
Path={base_dir}
Icon=utilities-system-monitor
Terminal=false
Categories=Development;
StartupNotify=false
X-GNOME-Autostart-enabled=true
"""

def is_autostart_enabled() -> bool:
    """Verifica se o Agent Cockpit está configurado para iniciar com o sistema."""
    if not AUTOSTART_FILE.exists():
        return False
    try:
        content = AUTOSTART_FILE.read_text(encoding="utf-8")
        if "X-GNOME-Autostart-enabled=false" in content or "Hidden=true" in content:
            return False
        return True
    except Exception:
        return False

def enable_autostart() -> bool:
    """Habilita a inicialização com o sistema operacional criando o arquivo .desktop no diretório autostart."""
    try:
        AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
        content = generate_desktop_entry_content()
        AUTOSTART_FILE.write_text(content, encoding="utf-8")
        AUTOSTART_FILE.chmod(0o755)

        try:
            APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
            APP_DESKTOP_FILE.write_text(content, encoding="utf-8")
            APP_DESKTOP_FILE.chmod(0o755)
        except Exception:
            pass

        return True
    except Exception as e:
        print(f"[Autostart] Erro ao habilitar autostart: {e}", file=sys.stderr)
        return False

def disable_autostart() -> bool:
    """Desabilita a inicialização com o sistema operacional removendo o arquivo .desktop de autostart."""
    try:
        if AUTOSTART_FILE.exists():
            AUTOSTART_FILE.unlink()
        return True
    except Exception as e:
        print(f"[Autostart] Erro ao desabilitar autostart: {e}", file=sys.stderr)
        return False

def get_autostart_info() -> Dict[str, Any]:
    """Retorna informações completas do estado de autostart para a API REST e UI."""
    enabled = is_autostart_enabled()
    base_dir, run_script, python_exec = get_cockpit_paths()
    return {
        "enabled": enabled,
        "supported": True,
        "platform": sys.platform,
        "method": "xdg_autostart",
        "file_path": str(AUTOSTART_FILE),
        "target_script": str(run_script),
        "python_executable": str(python_exec)
    }

def main():
    parser = argparse.ArgumentParser(description="Gerenciador de Inicialização com o Sistema para o Agent Cockpit")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true", help="Exibe o status atual do autostart")
    group.add_argument("--enable", action="store_true", help="Habilita inicialização automática com o sistema")
    group.add_argument("--disable", action="store_true", help="Desabilita inicialização automática com o sistema")

    args = parser.parse_args()

    if args.status:
        info = get_autostart_info()
        status_str = "HABILITADO" if info["enabled"] else "DESABILITADO"
        print(f"Agent Cockpit Autostart: {status_str}")
        print(f"Caminho do arquivo: {info['file_path']}")
        print(f"Script alvo: {info['target_script']}")
    elif args.enable:
        if enable_autostart():
            print(f"[OK] Agent Cockpit configurado com sucesso para iniciar com o sistema!")
            print(f"Arquivo gerado: {AUTOSTART_FILE}")
        else:
            print("[ERRO] Falha ao configurar autostart.", file=sys.stderr)
            sys.exit(1)
    elif args.disable:
        if disable_autostart():
            print(f"[OK] Inicialização automática com o sistema desabilitada com sucesso.")
        else:
            print("[ERRO] Falha ao desabilitar autostart.", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
