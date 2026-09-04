import os
import sys
import uvicorn

import argparse
import socket
import subprocess
import time

def inspect_process(pid: int):
    """Inspeciona o nome do executável e a linha de comando de um processo por PID."""
    name = "desconhecido"
    cmdline = ""
    if sys.platform == "win32":
        try:
            tl = subprocess.check_output(f'tasklist /FI "PID eq {pid}" /FO CSV /NH', shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in tl.strip().splitlines():
                if line.startswith('"'):
                    name = line.split('"')[1]
                    break
        except Exception:
            pass
        try:
            ps_cmd = f'powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object ProcessId -eq {pid}).CommandLine"'
            cmdline = subprocess.check_output(ps_cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            pass
    else:
        try:
            out = subprocess.check_output(["ps", "-p", str(pid), "-o", "comm=,args="], text=True, stderr=subprocess.DEVNULL).strip()
            if out:
                parts = out.split(None, 1)
                name = parts[0]
                cmdline = parts[1] if len(parts) > 1 else ""
        except Exception:
            pass
    return name, cmdline

def is_cockpit_process(name: str, cmdline: str) -> bool:
    """Verifica se o processo é comprovadamente uma instância do Agent Cockpit."""
    combined = f"{name} {cmdline}".lower()
    cockpit_keywords = ["run_cockpit", "web_server:app", "agent-cockpit", "start_cockpit", "server.web_server"]
    return any(k in combined for k in cockpit_keywords)

def handle_port_conflict(port: int = 8765, host: str = "127.0.0.1", force: bool = False) -> bool:
    """
    Verifica se a porta está ocupada.
    - Se for o próprio Agent Cockpit (instância zumbi/anterior): encerra e libera a porta com segurança.
    - Se for um processo alheio (ex: Postgres, Node, Docker): NÃO encerra e avisa o usuário.
    Retorna True se a porta está livre para uso, False caso contrário.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex((host, port)) != 0:
            return True  # Porta livre!

    current_pid = os.getpid()
    listening_pids = set()

    if sys.platform == "win32":
        try:
            out = subprocess.check_output(f'netstat -ano | findstr :{port}', shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in out.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in parts:
                    try:
                        p = int(parts[-1])
                        if p != current_pid:
                            listening_pids.add(p)
                    except ValueError:
                        pass
        except Exception:
            pass
    else:
        try:
            out = subprocess.check_output(f"lsof -ti :{port}", shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in out.strip().splitlines():
                try:
                    p = int(line)
                    if p != current_pid:
                        listening_pids.add(p)
                except ValueError:
                    pass
        except Exception:
            pass

    if not listening_pids:
        # Porta detectada como aberta mas não foi possível listar os PIDs (ex: permissões)
        return True

    # Inspeciona cada processo ouvindo na porta
    for pid in listening_pids:
        name, cmdline = inspect_process(pid)
        is_ours = is_cockpit_process(name, cmdline)

        if is_ours or force:
            print(f"[*] Instância anterior do Agent Cockpit detectada (PID {pid}: {name}). Encerrando para reiniciar...")
            if sys.platform == "win32":
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(f"kill -9 {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)
        else:
            print("=" * 70)
            print(f"[!] AVISO DE SEGURANÇA: A porta {port} já está em uso por outro aplicativo!")
            print(f"[*] Processo detectado: {name} (PID: {pid})")
            if cmdline:
                print(f"[*] Linha de comando:   {cmdline}")
            print(f"[*] Por segurança, este processo NÃO pertence ao Cockpit e NÃO foi finalizado.")
            print("\nO que você pode fazer:")
            print(f"  1. Fechar o aplicativo '{name}'")
            print(f"  2. Ou iniciar o Cockpit em outra porta executando:")
            print(f"     python run_cockpit.py --port {port + 1}")
            print("=" * 70)
            return False

    return True

def main():
    parser = argparse.ArgumentParser(description="Agent Cockpit Dashboard Server")
    parser.add_argument("--port", type=int, default=8765, help="Porta do servidor Web (padrão: 8765)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host de binding (padrão: 127.0.0.1)")
    parser.add_argument("--force", action="store_true", help="Forçar encerramento de qualquer processo na porta")
    args = parser.parse_args()

    port = args.port
    host = args.host

    if not handle_port_conflict(port=port, host=host, force=args.force):
        sys.exit(1)

    print("=" * 68)
    print("           AGENT COCKPIT - PAINEL OFFLINE EM TEMPO REAL           ")
    print("=" * 68)
    print(f"[*] Dashboard Web:   http://localhost:{port}")
    print(f"[*] WebSocket Feed:  ws://localhost:{port}/ws")
    print(f"[*] Servidor MCP:    agent-cockpit/server/mcp_server.py (stdio)")
    print("=" * 68)
    print("\n[Instruções de Conexão no Antigravity MCP]:")
    print("Adicione o servidor ao seu mcp_config.json:")
    print('''
{
  "mcpServers": {
    "agent-cockpit": {
      "command": "python",
      "args": ["''' + os.path.abspath(os.path.join(os.path.dirname(__file__), "server", "mcp_server.py")).replace("\\", "\\\\") + '''"]
    }
  }
}
''')
    print("=" * 68)
    print("Iniciando servidor local do Cockpit... Pressione Ctrl+C para encerrar.\n")

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))
    uvicorn.run("web_server:app", host=host, port=port, log_level="info")

if __name__ == "__main__":
    main()
