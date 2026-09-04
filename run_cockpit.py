import os
import sys
import uvicorn

def free_port(port: int = 8765):
    """Encerra qualquer processo anterior que esteja escutando na porta especificada."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", port)) != 0:
            return

    print(f"[*] Porta {port} ocupada. Liberando processo anterior...")
    current_pid = os.getpid()
    if sys.platform == "win32":
        import subprocess
        try:
            out = subprocess.check_output(
                f'netstat -ano | findstr :{port}',
                shell=True,
                text=True,
                stderr=subprocess.DEVNULL
            )
            killed = set()
            for line in out.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in parts:
                    try:
                        pid = int(parts[-1])
                        if pid != current_pid and pid not in killed:
                            subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            killed.add(pid)
                    except ValueError:
                        pass
            if killed:
                print(f"[+] Processo(s) anterior(es) encerrado(s): {list(killed)}")
                import time
                time.sleep(1)
        except Exception:
            pass
    else:
        import subprocess
        try:
            subprocess.run(f"fuser -k {port}/tcp", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            try:
                subprocess.run(f"kill -9 $(lsof -t -i:{port})", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

def main():
    port = 8765
    host = "127.0.0.1"

    free_port(port)

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
