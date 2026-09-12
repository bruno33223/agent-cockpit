import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

# Configura stdout para UTF-8 de forma segura no Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def print_banner():
    print("=" * 65)
    print("       >>> AGENT COCKPIT - INSTALADOR E CONFIGURADOR 1-CLIQUE <<<")
    print("=" * 65)

def check_python():
    print("\n[1/5] Verificando versao do Python...")
    v = sys.version_info
    print(f"      Python detectado: {v.major}.{v.minor}.{v.micro} ({sys.executable})")
    if v.major < 3 or (v.major == 3 and v.minor < 8):
        print("      [ERRO] E necessario Python 3.8 ou superior.")
        sys.exit(1)
    print("      [OK] Versao do Python compativel.")

def install_dependencies(base_dir):
    print("\n[2/5] Instalando dependencias (FastAPI, Uvicorn, WebSockets, Pydantic)...")
    req_file = os.path.join(base_dir, "requirements.txt")
    if os.path.exists(req_file):
        cmd = [sys.executable, "-m", "pip", "install", "-r", req_file]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 and ("externally-managed-environment" in (res.stdout + res.stderr)):
            cmd_fallback = [sys.executable, "-m", "pip", "install", "--user", "--break-system-packages", "-r", req_file]
            res = subprocess.run(cmd_fallback, capture_output=True, text=True)
        if res.returncode == 0:
            print("      [OK] Todas as dependencias foram instaladas com sucesso!")
        else:
            print("      [AVISO] Saida da instalacao:")
            print(res.stdout or res.stderr)
    else:
        print("      [PULADO] requirements.txt nao encontrado.")

def configure_mcp(base_dir):
    print("\n[3/5] Registrando Servidor MCP nas configuracoes da IA...")
    mcp_server_script = os.path.abspath(os.path.join(base_dir, "server", "mcp_server.py"))
    python_exec = sys.executable.replace("\\", "/")
    server_path = mcp_server_script.replace("\\", "/")

    home = Path.home()
    target_configs = []

    # 1. Antigravity Global
    antigravity_cfg1 = home / ".gemini" / "config" / "mcp_config.json"
    target_configs.append(("Antigravity (Global)", antigravity_cfg1))

    # 2. Antigravity AppData
    antigravity_cfg2 = home / ".gemini" / "antigravity" / "mcp_config.json"
    target_configs.append(("Antigravity (AppData)", antigravity_cfg2))

    # 3. Claude Desktop
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            claude_cfg = Path(appdata) / "Claude" / "claude_desktop_config.json"
            target_configs.append(("Claude Desktop", claude_cfg))
    elif sys.platform == "darwin":
        claude_cfg = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        target_configs.append(("Claude Desktop", claude_cfg))
    else:
        claude_cfg = home / ".config" / "Claude" / "claude_desktop_config.json"
        target_configs.append(("Claude Desktop", claude_cfg))

    configured_count = 0
    for label, cfg_path in target_configs:
        try:
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if cfg_path.exists():
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
                data["mcpServers"] = {}

            data["mcpServers"]["agent-cockpit"] = {
                "command": python_exec,
                "args": [server_path]
            }

            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"      [OK] Configurado em {label}: {cfg_path}")
            configured_count += 1
        except Exception as e:
            print(f"      [AVISO] Nao foi possivel gravar em {cfg_path}: {e}")

    if configured_count == 0:
        print("      [!] Nao foi possivel gravar automaticamente.")
        print("      Adicione manualmente ao seu mcp_config.json:")
        manual = {
            "mcpServers": {
                "agent-cockpit": {
                    "command": python_exec,
                    "args": [server_path]
                }
            }
        }
        print(json.dumps(manual, indent=2))

def export_mcp_schemas(base_dir):
    print("\n[3.5/5] Gerando schemas de ferramentas MCP para Antigravity Lazy-Loading...")
    sys.path.insert(0, os.path.join(base_dir, "server"))
    try:
        from mcp_server import TOOLS_DEFINITIONS
        mcp_schema_dir = Path.home() / ".gemini" / "antigravity" / "mcp" / "agent-cockpit"
        mcp_schema_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for tool in TOOLS_DEFINITIONS:
            schema_data = {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}})
            }
            target_json = mcp_schema_dir / f"{tool['name']}.json"
            with open(target_json, "w", encoding="utf-8") as f:
                json.dump(schema_data, f, ensure_ascii=False, indent=2)
            count += 1
        print(f"      [OK] {count} schemas de ferramentas MCP gerados em: {mcp_schema_dir}")
    except Exception as e:
        print(f"      [AVISO] Erro ao exportar schemas MCP: {e}")

def configure_autostart(base_dir, enable=None):
    print("\n[5/5] Configurando inicializacao automatica com o sistema operacional...")
    sys.path.insert(0, os.path.join(base_dir, "server"))
    try:
        import autostart
        if enable is None:
            if sys.stdin.isatty():
                try:
                    resp = input("      Deseja iniciar o Agent Cockpit automaticamente ao ligar o computador? (S/n): ").strip().lower()
                    enable = resp != "n"
                except Exception:
                    enable = True
            else:
                enable = True

        if enable:
            if autostart.enable_autostart():
                print(f"      [OK] Inicializacao automatica configurada com sucesso!")
                print(f"      Arquivo registrado: {autostart.AUTOSTART_FILE}")
                # Recarrega e inicia o servico systemd se estiver no Linux
                if sys.platform.startswith("linux"):
                    try:
                        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
                        subprocess.run(["systemctl", "--user", "restart", "agent-cockpit.service"], check=False)
                        print("      [OK] Servico systemd agent-cockpit.service iniciado com sucesso!")
                    except Exception as e:
                        print(f"      [AVISO] Nao foi possivel reiniciar o servico systemd: {e}")
            else:
                print("      [AVISO] Nao foi possivel configurar o autostart.")
        else:
            autostart.disable_autostart()
            print("      [INFO] Inicializacao automatica desativada conforme solicitado.")
    except Exception as e:
        print(f"      [AVISO] Erro ao configurar autostart: {e}")

def copy_skills(base_dir):
    print("\n[4/5] Instalando Skills do Cockpit e Superpowers...")
    skills_src = os.path.join(base_dir, "skills")
    if not os.path.exists(skills_src):
        print("      [PULADO] Pasta skills/ nao encontrada no pacote.")
        return

    dest_skills = Path.home() / ".gemini" / "config" / "skills"
    try:
        dest_skills.mkdir(parents=True, exist_ok=True)
        installed_skills = []
        for item in os.listdir(skills_src):
            src = os.path.join(skills_src, item)
            if os.path.isdir(src):
                dst = dest_skills / item
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                installed_skills.append(item)
        print(f"      [OK] Total de {len(installed_skills)} skills instaladas com sucesso (Cockpit + Superpowers)!")
    except Exception as e:
        print(f"      [AVISO] Nao foi possivel copiar skills automaticamente: {e}")

def uninstall_cockpit(base_dir):
    print("=" * 65)
    print("       >>> AGENT COCKPIT - DESINSTALADOR <<<")
    print("=" * 65)

    home = Path.home()
    # 1. Parar e desabilitar systemd service
    print("\n[1/4] Desativando servicos do sistema...")
    sys.path.insert(0, os.path.join(base_dir, "server"))
    try:
        import autostart
        autostart.disable_autostart()
        print("      [OK] Autostart desativado.")
    except Exception as e:
        print(f"      [AVISO] Falha ao desativar autostart: {e}")

    if sys.platform.startswith("linux"):
        try:
            subprocess.run(["systemctl", "--user", "stop", "agent-cockpit.service"], capture_output=True, check=False)
            subprocess.run(["systemctl", "--user", "disable", "agent-cockpit.service"], capture_output=True, check=False)
            svc_file = home / ".config" / "systemd" / "user" / "agent-cockpit.service"
            if svc_file.exists():
                svc_file.unlink()
            subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, check=False)
            print("      [OK] Servico systemd parado e removido.")
        except Exception as e:
            print(f"      [AVISO] Erro ao limpar systemd: {e}")

    # 2. Remover schemas MCP e limpar mcp_config.json
    print("\n[2/4] Removendo configuracoes e schemas MCP...")
    mcp_schema_dir = home / ".gemini" / "antigravity" / "mcp" / "agent-cockpit"
    if mcp_schema_dir.exists():
        shutil.rmtree(mcp_schema_dir)
        print(f"      [OK] Removido diretorio de schemas: {mcp_schema_dir}")

    target_configs = [
        home / ".gemini" / "config" / "mcp_config.json",
        home / ".gemini" / "antigravity" / "mcp_config.json",
    ]
    for cfg in target_configs:
        if cfg.exists():
            try:
                with open(cfg, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "mcpServers" in data and "agent-cockpit" in data["mcpServers"]:
                    del data["mcpServers"]["agent-cockpit"]
                    with open(cfg, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    print(f"      [OK] Removido registro de {cfg}")
            except Exception as e:
                print(f"      [AVISO] Falha ao atualizar {cfg}: {e}")

    # 3. Remover skills instaladas
    print("\n[3/4] Removendo skills instaladas...")
    skills_src = os.path.join(base_dir, "skills")
    dest_skills = home / ".gemini" / "config" / "skills"
    if os.path.exists(skills_src) and dest_skills.exists():
        removed_count = 0
        for item in os.listdir(skills_src):
            target = dest_skills / item
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                removed_count += 1
        print(f"      [OK] {removed_count} skills removidas de {dest_skills}")

    print("\n[4/4] Finalizando desinstalacao...")
    print("\n" + "=" * 65)
    print("       >>> DESINSTALACAO CONCLUIDA COM SUCESSO! <<<")
    print("=" * 65)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Instalador e Desinstalador do Agent Cockpit")
    parser.add_argument("--autostart", dest="autostart", action="store_true", default=None, help="Ativar inicializacao automatica com o sistema")
    parser.add_argument("--no-autostart", dest="autostart", action="store_false", help="Nao ativar inicializacao automatica com o sistema")
    parser.add_argument("--uninstall", action="store_true", help="Desinstalar o Agent Cockpit (servico, skills, mcp)")
    parser.add_argument("--reinstall", action="store_true", help="Desinstalar versao anterior e reinstalar limpa")
    args, _ = parser.parse_known_args()

    base_dir = os.path.abspath(os.path.dirname(__file__))

    if args.uninstall:
        uninstall_cockpit(base_dir)
        return

    if args.reinstall:
        uninstall_cockpit(base_dir)
        print("\nIniciando nova instalacao limpa...\n")

    print_banner()
    check_python()
    install_dependencies(base_dir)
    configure_mcp(base_dir)
    export_mcp_schemas(base_dir)
    copy_skills(base_dir)
    configure_autostart(base_dir, enable=args.autostart)

    print("\n" + "=" * 65)
    print("       >>> INSTALACAO CONCLUIDA COM SUCESSO! <<<")
    print("=" * 65)
    print("\nComo usar:")
    print("  1. Inicie o Dashboard:")
    print("     - No Terminal / Linux: python3 run_cockpit.py")
    print("     - Ou utilize o icone gerado no menu de aplicativos do Linux")
    print("     - No Windows: De 2 cliques em 'start_cockpit.bat'")
    print("  2. Acesse no Navegador: http://localhost:8765")
    print("  3. Inicializacao com o Sistema:")
    print("     - Status: python3 run_cockpit.py --autostart-status")
    print("     - Alternar: via painel Web (http://localhost:8765) ou CLI")
    print("  4. No chat da IA (Antigravity ou Claude):")
    print('     \"Ative a skill /cockpit e execute meu projeto com /spec-orchestrator\"')
    print("\n" + "=" * 65)

if __name__ == "__main__":
    main()
