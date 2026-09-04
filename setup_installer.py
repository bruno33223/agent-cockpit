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
    print("\n[1/4] Verificando versao do Python...")
    v = sys.version_info
    print(f"      Python detectado: {v.major}.{v.minor}.{v.micro} ({sys.executable})")
    if v.major < 3 or (v.major == 3 and v.minor < 8):
        print("      [ERRO] E necessario Python 3.8 ou superior.")
        sys.exit(1)
    print("      [OK] Versao do Python compativel.")

def install_dependencies(base_dir):
    print("\n[2/4] Instalando dependencias (FastAPI, Uvicorn, WebSockets, Pydantic)...")
    req_file = os.path.join(base_dir, "requirements.txt")
    if os.path.exists(req_file):
        cmd = [sys.executable, "-m", "pip", "install", "-r", req_file]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print("      [OK] Todas as dependencias foram instaladas com sucesso!")
        else:
            print("      [AVISO] Saida da instalacao:")
            print(res.stdout or res.stderr)
    else:
        print("      [PULADO] requirements.txt nao encontrado.")

def configure_mcp(base_dir):
    print("\n[3/4] Registrando Servidor MCP nas configuracoes da IA...")
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

def copy_skills(base_dir):
    print("\n[4/4] Instalando Skills do Cockpit e Spec-Orchestrator...")
    skills_src = os.path.join(base_dir, "skills")
    if not os.path.exists(skills_src):
        print("      [PULADO] Pasta skills/ nao encontrada no pacote.")
        return

    dest_skills = Path.home() / ".gemini" / "config" / "skills"
    try:
        dest_skills.mkdir(parents=True, exist_ok=True)
        for skill_name in ["cockpit", "spec-orchestrator", "gauntlet-loop"]:
            src = os.path.join(skills_src, skill_name)
            dst = dest_skills / skill_name
            if os.path.exists(src):
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                print(f"      [OK] Skill '{skill_name}' instalada com sucesso!")
    except Exception as e:
        print(f"      [AVISO] Nao foi possivel copiar skills automaticamente: {e}")

def main():
    base_dir = os.path.abspath(os.path.dirname(__file__))
    print_banner()
    check_python()
    install_dependencies(base_dir)
    configure_mcp(base_dir)
    copy_skills(base_dir)

    print("\n" + "=" * 65)
    print("       >>> INSTALACAO CONCLUIDA COM SUCESSO! <<<")
    print("=" * 65)
    print("\nComo usar:")
    print("  1. Inicie o Dashboard:")
    print("     - No Windows: De 2 cliques em 'start_cockpit.bat'")
    print("     - No Terminal: python run_cockpit.py")
    print("  2. Acesse no Navegador: http://localhost:8765")
    print("  3. No chat da IA (Antigravity ou Claude):")
    print('     \"Ative a skill /cockpit e execute meu projeto com /spec-orchestrator\"')
    print("\n" + "=" * 65)

if __name__ == "__main__":
    main()
