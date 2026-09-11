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

# Caminhos Systemd User Service (Nativo e persistente no Linux)
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
SYSTEMD_SERVICE_NAME = "agent-cockpit.service"
SYSTEMD_SERVICE_FILE = SYSTEMD_USER_DIR / SYSTEMD_SERVICE_NAME

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

def generate_systemd_unit_content() -> str:
    """Gera a unit de serviço systemd para execução gerenciada em background com auto-restart."""
    base_dir, run_script, python_exec = get_cockpit_paths()
    return f"""[Unit]
Description=Agent Cockpit Telemetry & Governance Server
After=network.target

[Service]
Type=simple
ExecStart={python_exec} {run_script}
WorkingDirectory={base_dir}
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""

def is_systemd_service_enabled() -> bool:
    """Verifica se o serviço systemd de usuário está configurado e habilitado."""
    if not SYSTEMD_SERVICE_FILE.exists():
        return False
    try:
        import subprocess
        res = subprocess.run(
            ["systemctl", "--user", "is-enabled", SYSTEMD_SERVICE_NAME],
            capture_output=True,
            text=True,
            check=False
        )
        return res.returncode == 0 or "enabled" in res.stdout
    except Exception:
        return SYSTEMD_SERVICE_FILE.exists()

def is_autostart_enabled() -> bool:
    """Verifica se o Agent Cockpit está configurado para iniciar com o sistema."""
    if is_systemd_service_enabled():
        return True

    if AUTOSTART_FILE.exists():
        try:
            content = AUTOSTART_FILE.read_text(encoding="utf-8")
            if "X-GNOME-Autostart-enabled=false" in content or "Hidden=true" in content:
                return False
            return True
        except Exception:
            return False
    return False

def enable_autostart() -> bool:
    """Habilita a inicialização com o sistema criando serviço systemd e entrada .desktop."""
    import subprocess
    success = False
    try:
        # 1. Systemd User Service
        SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
        content = generate_systemd_unit_content()
        SYSTEMD_SERVICE_FILE.write_text(content, encoding="utf-8")
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, check=False)
        subprocess.run(["systemctl", "--user", "enable", "--now", SYSTEMD_SERVICE_NAME], capture_output=True, check=False)
        success = True
    except Exception as e:
        print(f"[Autostart] Aviso systemd: {e}", file=sys.stderr)

    try:
        # 2. XDG FreeDesktop Autostart
        AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
        d_content = generate_desktop_entry_content()
        AUTOSTART_FILE.write_text(d_content, encoding="utf-8")
        AUTOSTART_FILE.chmod(0o755)

        try:
            APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
            APP_DESKTOP_FILE.write_text(d_content, encoding="utf-8")
            APP_DESKTOP_FILE.chmod(0o755)
        except Exception:
            pass
        success = True
    except Exception as e:
        print(f"[Autostart] Aviso desktop: {e}", file=sys.stderr)

    return success

def disable_autostart() -> bool:
    """Desabilita a inicialização com o sistema removendo o serviço systemd e o arquivo .desktop."""
    import subprocess
    try:
        # 1. Desabilita systemd
        subprocess.run(["systemctl", "--user", "disable", "--now", SYSTEMD_SERVICE_NAME], capture_output=True, check=False)
        if SYSTEMD_SERVICE_FILE.exists():
            SYSTEMD_SERVICE_FILE.unlink()
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, check=False)

        # 2. Remove .desktop
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
        "method": "systemd_user + xdg_autostart",
        "service_file": str(SYSTEMD_SERVICE_FILE),
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
        print(f"Método: {info['method']}")
        print(f"Systemd Service: {info['service_file']}")
        print(f"XDG Desktop: {info['file_path']}")
        print(f"Script alvo: {info['target_script']}")
    elif args.enable:
        if enable_autostart():
            print(f"[OK] Agent Cockpit configurado com sucesso para iniciar com o sistema!")
            print(f"Serviço systemd: {SYSTEMD_SERVICE_FILE}")
            print(f"Arquivo desktop: {AUTOSTART_FILE}")
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
