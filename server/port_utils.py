"""
port_utils.py: Utilitários nativos de verificação de portas e resolução de conflitos.
Diferencia conexões ativas reais (LISTEN) de estados transitórios (TIME_WAIT).
"""

import os
import sys
import time
import socket
import subprocess
from typing import Set, Tuple


def has_listening_socket(port: int, host: str = "127.0.0.1") -> bool:
    """
    Verifica se existe algum socket TCP ativo no estado LISTEN para a porta especificada.
    - No Linux: inspeciona /proc/net/tcp e /proc/net/tcp6 para checar estado 0A (TCP_LISTEN).
    - Em outras plataformas ou como fallback: consulta 'ss' ou 'netstat' filtrando por LISTEN.
    """
    hex_port = f"{port:04X}"
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                next(f, None)
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        local_addr = parts[1]
                        state = parts[3]
                        if local_addr.endswith(f":{hex_port}") and state == "0A":
                            return True
        except (FileNotFoundError, PermissionError, OSError):
            pass

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
    e SO_REUSEPORT (quando suportado na plataforma).
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
    - Retorna True se a porta está livre para uso, False caso contrário.
    """
    if not has_listening_socket(port=port, host=host) and not is_port_in_use(port=port, host=host):
        return True

    current_pid = os.getpid()
    listening_pids: Set[int] = set()

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

    def _inspect_process(pid: int) -> Tuple[str, str]:
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
                p_out = subprocess.check_output(["ps", "-p", str(pid), "-o", "comm=,args="], text=True, stderr=subprocess.DEVNULL).strip()
                if p_out:
                    parts = p_out.split(None, 1)
                    name = parts[0]
                    cmdline = parts[1] if len(parts) > 1 else ""
            except Exception:
                pass
        return name, cmdline

    def _is_cockpit_proc(name: str, cmdline: str) -> bool:
        combined = f"{name} {cmdline}".lower()
        cockpit_keywords = ["run_cockpit", "web_server:app", "agent-cockpit", "start_cockpit", "server.web_server"]
        return any(k in combined for k in cockpit_keywords)

    if not listening_pids:
        if has_listening_socket(port=port, host=host) or is_port_in_use(port=port, host=host):
            print("=" * 70)
            print(f"[!] AVISO DE CONFLITO: A porta {port} está ocupada no host {host}, mas não foi possível listar o PID.")
            print(f"[*] Pode ser necessário privilégio de root/administrador ou outro serviço do sistema.")
            print("=" * 70)
            return False
        return True

    for pid in listening_pids:
        name, cmdline = _inspect_process(pid)
        is_ours = _is_cockpit_proc(name, cmdline)

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
            print("=" * 70)
            return False

    if has_listening_socket(port=port, host=host):
        time.sleep(0.5)
    return not has_listening_socket(port=port, host=host) and not is_port_in_use(port=port, host=host)
