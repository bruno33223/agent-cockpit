import os
import sys
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

def has_listening_socket(port: int, host: str = "127.0.0.1") -> bool:
    """
    Verifica se existe algum socket TCP ativo no estado LISTEN para a porta especificada.
    - No Linux: inspeciona /proc/net/tcp e /proc/net/tcp6 para checar estado 0A (TCP_LISTEN).
      Isso funciona mesmo sem privilégios de root, diferenciando conexões residuais em
      TIME_WAIT (estado 06) de processos ouvintes reais (estado 0A).
    - Em outras plataformas ou como fallback: consulta 'ss' ou 'netstat' filtrando por LISTEN.
    Retorna True se houver socket ativo no estado LISTEN, False caso contrário.
    """
    hex_port = f"{port:04X}"
    # 1. Inspeciona /proc/net/tcp e /proc/net/tcp6 (Linux)
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                next(f, None)  # Pula o cabeçalho
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        local_addr = parts[1]
                        state = parts[3]
                        # Verifica porta local e estado 0A (TCP_LISTEN)
                        if local_addr.endswith(f":{hex_port}") and state == "0A":
                            return True
        except (FileNotFoundError, PermissionError, OSError):
            pass

    # 2. Fallback via 'ss' (Linux) ou 'netstat' (Windows)
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(f'netstat -ano | findstr :{port}', shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in out.strip().splitlines():
                if "LISTENING" in line:
                    return True
        except Exception:
            pass
    else:
        try:
            out = subprocess.check_output(f"ss -tlnH sport = :{port}", shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            if out:
                return True
        except Exception:
            pass

    return False

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """
    Verifica se a porta está em uso utilizando bind nativo via socket com SO_REUSEADDR
    e SO_REUSEPORT (quando disponível na plataforma).
    Retorna True se a porta estiver ocupada / em uso, ou False se estiver livre para bind.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            s.bind((host, port))
            return False
        except (OSError, socket.error):
            return True

def create_bound_socket(host: str = "127.0.0.1", port: int = 8765, backlog: int = 128) -> socket.socket:
    """
    Cria, configura e vincula um socket TCP pré-vinculado com SO_REUSEADDR
    e SO_REUSEPORT (quando suportado na plataforma) para inicialização imediata
    e resiliente do servidor Uvicorn, prevenindo erros de porta ocupada por TIME_WAIT.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    sock.bind((host, port))
    sock.listen(backlog)
    return sock

def handle_port_conflict(port: int = 8765, host: str = "127.0.0.1", force: bool = False) -> bool:
    """
    Verifica se a porta está ocupada de forma robusta e segura.
    - Diferencia conexões ativas reais com processo ouvinte (LISTEN) de estados transitórios (TIME_WAIT).
    - Utiliza verificação nativa de socket bind (SO_REUSEADDR e SO_REUSEPORT).
    - Se for o próprio Agent Cockpit (instância zumbi/anterior): encerra e libera a porta com segurança.
    - Se for um processo alheio (ex: Postgres, Node, Docker): NÃO encerra e avisa o usuário.
    Retorna True se a porta está livre para uso, False caso contrário.
    """
    # 1. Se não houver socket em LISTEN e o bind for bem-sucedido, porta 100% livre!
    if not has_listening_socket(port=port, host=host) and not is_port_in_use(port=port, host=host):
        return True

    # 2. A porta parece em uso ou há ouvinte em escuta. Identifica processos ouvintes.
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
            out = subprocess.check_output(f"lsof -iTCP:{port} -sTCP:LISTEN -t", shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in out.strip().splitlines():
                try:
                    p = int(line)
                    if p != current_pid:
                        listening_pids.add(p)
                except ValueError:
                    pass
        except Exception:
            pass

    # 3. Se nenhum PID foi listado (ex: lsof falhou por falta de permissão):
    if not listening_pids:
        # Se houver socket ativo em LISTEN ou o bind não puder ser realizado:
        if has_listening_socket(port=port, host=host) or is_port_in_use(port=port, host=host):
            print("=" * 70)
            print(f"[!] AVISO DE CONFLITO: A porta {port} está ocupada no host {host}, mas não foi possível listar o PID.")
            print(f"[*] Pode ser necessário privilégio de root/administrador ou outro serviço do sistema.")
            print("=" * 70)
            return False
        # Caso contrário, apenas estados transitórios (TIME_WAIT) sem ouvinte: porta livre!
        return True

    # 4. Inspeciona cada processo ouvindo na porta
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

    # 5. Verificação final após encerramento do Cockpit anterior
    if has_listening_socket(port=port, host=host):
        time.sleep(0.5)
    return not has_listening_socket(port=port, host=host) and not is_port_in_use(port=port, host=host)

def cleanup_orphan_cockpit_processes(timeout: float = 2.0) -> list:
    """Varre e encerra processos órfãos (zumbis) com assinatura do Cockpit deixados por sessões anteriores."""
    try:
        from server.process_lifecycle import scan_and_cleanup_orphans
        return scan_and_cleanup_orphans(timeout=timeout)
    except Exception as e:
        print(f"[*] Aviso ao varrer processos órfãos: {e}", file=sys.stderr)
        return []
def start_server(host: str = "127.0.0.1", port: int = 8765):
    """
    Inicializa o servidor Uvicorn com socket pré-vinculado com SO_REUSEADDR e SO_REUSEPORT,
    permitindo reinicializações imediatas e resilientes sem bloqueios de TIME_WAIT.
    """
    try:
        import uvicorn
    except ImportError:
        print("[ERRO] Uvicorn não está instalado. Execute primeiro: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))
    server_sock = create_bound_socket(host=host, port=port)
    config = uvicorn.Config("web_server:app", host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    try:
        server.run(sockets=[server_sock])
    finally:
        try:
            server_sock.close()
        except Exception:
            pass

def main():
    parser = argparse.ArgumentParser(description="Agent Cockpit Dashboard Server")
    parser.add_argument("--port", type=int, default=8765, help="Porta do servidor Web (padrão: 8765)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host de binding (padrão: 127.0.0.1)")
    parser.add_argument("--force", action="store_true", help="Forçar encerramento de qualquer processo na porta")
    parser.add_argument("--autostart-enable", action="store_true", help="Configura o Agent Cockpit para iniciar com o sistema operacional")
    parser.add_argument("--autostart-disable", action="store_true", help="Desativa a inicialização do Agent Cockpit com o sistema operacional")
    parser.add_argument("--autostart-status", action="store_true", help="Verifica se o Agent Cockpit está configurado para iniciar com o sistema")
    parser.add_argument("--no-ollama", action="store_true", help="Desativa a inicialização automática do Ollama em segundo plano")
    args = parser.parse_args()

    if args.no_ollama:
        os.environ["COCKPIT_NO_OLLAMA"] = "1"

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))
    if args.autostart_enable or args.autostart_disable or args.autostart_status:
        import autostart
        if args.autostart_enable:
            if autostart.enable_autostart():
                print(f"[OK] Agent Cockpit configurado para iniciar com o sistema operacional ({autostart.AUTOSTART_FILE})")
            else:
                print("[ERRO] Falha ao configurar autostart.", file=sys.stderr)
                sys.exit(1)
        elif args.autostart_disable:
            if autostart.disable_autostart():
                print("[OK] Inicialização automática com o sistema desativada com sucesso.")
            else:
                print("[ERRO] Falha ao desativar autostart.", file=sys.stderr)
                sys.exit(1)
        elif args.autostart_status:
            status = "HABILITADO" if autostart.is_autostart_enabled() else "DESABILITADO"
            print(f"Agent Cockpit Autostart: {status} ({autostart.AUTOSTART_FILE})")
        sys.exit(0)

    # Varredura preventiva de processos órfãos deixados por sessões anteriores
    cleaned = cleanup_orphan_cockpit_processes()
    if cleaned:
        print(f"[*] Processos órfãos de sessões anteriores limpos no boot: {len(cleaned)} finalizados.")

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

    start_server(host=host, port=port)

if __name__ == "__main__":
    main()
