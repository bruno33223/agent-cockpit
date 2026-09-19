"""
process_lifecycle.py: Gerenciador unificado de ciclo de vida de processos e eliminação
de processos zumbis / órfãos no Agent Cockpit (MCP stdio, PTYs e workers).
"""

import os
import sys
import time
import signal
import socket
import threading
import subprocess
from typing import Dict, Any, List, Set, Optional, Tuple

try:
    import psutil
except ImportError:
    psutil = None


def is_pid_alive(pid: int) -> bool:
    """Verifica se um PID ainda está vivo no sistema operacional (e não é zumbi)."""
    if pid <= 0:
        return False
    if psutil is not None:
        try:
            p = psutil.Process(pid)
            return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OSError):
        return False

    if sys.platform != "win32":
        try:
            status_file = f"/proc/{pid}/status"
            if os.path.isfile(status_file):
                with open(status_file, "r") as f:
                    for line in f:
                        if line.startswith("State:"):
                            if "Z" in line:
                                return False
                            break
        except Exception:
            pass

    return True


def get_process_children(parent_pid: int) -> List[int]:
    """Retorna recursivamente a lista de PIDs filhos de um processo."""
    children_pids = []
    if psutil is not None:
        try:
            parent = psutil.Process(parent_pid)
            for child in parent.children(recursive=True):
                children_pids.append(child.pid)
            return children_pids
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return []

    # Fallback POSIX via comando ps
    if sys.platform != "win32":
        try:
            out = subprocess.check_output(
                ["ps", "--ppid", str(parent_pid), "-o", "pid="],
                text=True,
                stderr=subprocess.DEVNULL
            ).strip()
            if out:
                for line in out.splitlines():
                    try:
                        cpid = int(line.strip())
                        children_pids.append(cpid)
                        # Busca recursiva para os netos
                        children_pids.extend(get_process_children(cpid))
                    except ValueError:
                        pass
        except Exception:
            pass

    return children_pids


def terminate_process_tree(parent_pid: int, timeout: float = 3.0) -> List[int]:
    """
    Encerra em cascata uma árvore de processos (pai e todos os seus filhos).
    Executa encerramento gracioso com SIGTERM e fallback para SIGKILL após timeout.
    Retorna a lista de PIDs encerrados.
    """
    if parent_pid <= 0 or not is_pid_alive(parent_pid):
        return []

    # Coleta todos os descendentes
    descendants = get_process_children(parent_pid)
    all_pids = descendants + [parent_pid]
    terminated = []

    # 1. Envia SIGTERM para todos os processos da árvore
    for pid in all_pids:
        if is_pid_alive(pid):
            try:
                if sys.platform == "win32":
                    subprocess.run(f"taskkill /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    # Tenta matar pelo grupo de processo se for líder de grupo
                    try:
                        pgid = os.getpgid(pid)
                        if pgid == pid:
                            os.killpg(pgid, signal.SIGTERM)
                    except Exception:
                        pass
                    os.kill(pid, signal.SIGTERM)
                terminated.append(pid)
            except (ProcessLookupError, OSError):
                pass

    # 2. Aguarda até timeout para verificar encerramento
    deadline = time.time() + timeout
    while time.time() < deadline:
        if sys.platform != "win32":
            for p in all_pids:
                try:
                    os.waitpid(p, os.WNOHANG)
                except (ChildProcessError, ProcessLookupError, OSError):
                    pass
        alive = [p for p in all_pids if is_pid_alive(p)]
        if not alive:
            break
        time.sleep(0.05)

    # 3. Fallback SIGKILL para quaisquer processos resistentes que sobreviveram
    still_alive = [p for p in all_pids if is_pid_alive(p)]
    for pid in still_alive:
        try:
            if sys.platform == "win32":
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                try:
                    pgid = os.getpgid(pid)
                    if pgid == pid:
                        os.killpg(pgid, signal.SIGKILL)
                except Exception:
                    pass
                os.kill(pid, signal.SIGKILL)
            if pid not in terminated:
                terminated.append(pid)
        except (ProcessLookupError, OSError):
            pass

    # Reaping final direcionado
    if sys.platform != "win32":
        for _ in range(5):
            for p in all_pids:
                try:
                    os.waitpid(p, os.WNOHANG)
                except (ChildProcessError, ProcessLookupError, OSError):
                    pass
            time.sleep(0.02)

    return terminated


def inspect_process(pid: int) -> Tuple[str, str]:
    """Inspeciona o nome do executável e linha de comando de um PID."""
    name = "desconhecido"
    cmdline = ""
    if psutil is not None:
        try:
            p = psutil.Process(pid)
            name = p.name()
            cmdline = " ".join(p.cmdline())
            return name, cmdline
        except Exception:
            pass

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


def is_orphan_cockpit_process(pid: int, custom_keywords: Optional[List[str]] = None) -> bool:
    """
    Verifica se um processo possui assinatura do Cockpit e é órfão ou zumbi.
    Processos com PPID == 1 no Linux ou cujo processo pai encerrou são considerados órfãos.
    """
    curr_pid = os.getpid()
    if pid == curr_pid:
        return False

    name, cmdline = inspect_process(pid)
    combined = f"{name} {cmdline}".lower()

    if custom_keywords:
        for kw in custom_keywords:
            if kw.lower() in combined:
                return True

    cockpit_signatures = [
        "mcp_server.py",
        "server/mcp_server",
        "agent-cockpit",
        "cockpit_pty",
        "agent_cockpit_pty"
    ]

    has_signature = any(sig in combined for sig in cockpit_signatures)
    if not has_signature:
        return False

    # Verifica se é órfão
    if sys.platform != "win32":
        try:
            ppid_str = subprocess.check_output(["ps", "-p", str(pid), "-o", "ppid="], text=True, stderr=subprocess.DEVNULL).strip()
            if ppid_str:
                ppid = int(ppid_str)
                # PPID 1 é init/systemd -> processo órfão que foi adotado
                if ppid == 1 or not is_pid_alive(ppid):
                    return True
        except Exception:
            pass
    else:
        # No Windows, verifica se o pai ainda está ativo
        if psutil is not None:
            try:
                p = psutil.Process(pid)
                parent = p.parent()
                if parent is None or not parent.is_running():
                    return True
            except Exception:
                return True

    return False


def scan_and_cleanup_orphans(custom_keywords: Optional[List[str]] = None, timeout: float = 2.0) -> List[int]:
    """
    Varre todos os processos do sistema em busca de zumbis/órfãos do Cockpit e os encerra.
    """
    curr_pid = os.getpid()
    candidate_pids: Set[int] = set()

    if psutil is not None:
        try:
            for p in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    p_info = p.info
                    pid = p_info['pid']
                    if pid != curr_pid and is_orphan_cockpit_process(pid, custom_keywords=custom_keywords):
                        candidate_pids.add(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass

    if not candidate_pids and sys.platform != "win32":
        try:
            out = subprocess.check_output(["ps", "-eo", "pid"], text=True, stderr=subprocess.DEVNULL)
            for line in out.strip().splitlines()[1:]:
                try:
                    pid = int(line.strip())
                    if pid != curr_pid and is_orphan_cockpit_process(pid, custom_keywords=custom_keywords):
                        candidate_pids.add(pid)
                except ValueError:
                    pass
        except Exception:
            pass

    cleaned_pids = []
    for pid in candidate_pids:
        terminated = terminate_process_tree(pid, timeout=timeout)
        cleaned_pids.extend(terminated)

    return cleaned_pids


class ProcessLifecycleManager:
    """
    Gerenciador centralizado de processos filhos, instâncias MCP e terminais PTY.
    Garante encerramento assíncrono em cascata sem processos zumbis.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._registered_processes: Dict[int, Dict[str, Any]] = {}
        self._registered_mcps: Dict[int, Dict[str, Any]] = {}

    @property
    def registered_pids(self) -> Set[int]:
        with self._lock:
            return set(self._registered_processes.keys())

    @property
    def registered_mcps(self) -> Set[int]:
        with self._lock:
            return set(self._registered_mcps.keys())

    def register_process(self, pid_or_proc: Any, name: str = "child_process"):
        pid = pid_or_proc.pid if hasattr(pid_or_proc, "pid") else int(pid_or_proc)
        with self._lock:
            self._registered_processes[pid] = {
                "name": name,
                "registered_at": time.time()
            }

    def register_mcp_instance(self, pid_or_proc: Any, server_name: str = "mcp_server"):
        pid = pid_or_proc.pid if hasattr(pid_or_proc, "pid") else int(pid_or_proc)
        with self._lock:
            self.register_process(pid, name=f"mcp:{server_name}")
            self._registered_mcps[pid] = {
                "server_name": server_name,
                "registered_at": time.time()
            }

    def unregister_process(self, pid: int):
        with self._lock:
            self._registered_processes.pop(pid, None)
            self._registered_mcps.pop(pid, None)

    def shutdown(self, timeout: float = 3.0):
        """
        Encerra graciosamente todos os processos registrados e os filhos do processo atual.
        """
        curr_pid = os.getpid()
        with self._lock:
            targets = set(self._registered_processes.keys()) | set(self._registered_mcps.keys())
            # Adiciona filhos do processo atual
            targets.update(get_process_children(curr_pid))

        for pid in targets:
            terminate_process_tree(pid, timeout=timeout)

        with self._lock:
            self._registered_processes.clear()
            self._registered_mcps.clear()


_default_lifecycle_manager: Optional[ProcessLifecycleManager] = None
_manager_lock = threading.Lock()


def get_process_lifecycle_manager() -> ProcessLifecycleManager:
    global _default_lifecycle_manager
    with _manager_lock:
        if _default_lifecycle_manager is None:
            _default_lifecycle_manager = ProcessLifecycleManager()
        return _default_lifecycle_manager
