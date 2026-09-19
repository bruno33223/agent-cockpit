"""
pty_manager.py: Gerenciador multi-sessão de pseudo-terminais (PTY) concorrentes.
Permite executar múltiplos terminais paralelos (OpenCode, Claude Code, bash, pytest),
com persistência de histórico para reattach instantâneo, controle de dimensões (resize)
e desacoplamento do ciclo de vida dos processos.
"""

import os
import sys
import time
import json
import fcntl
import termios
import struct
import signal
import asyncio
from collections import deque
from typing import Dict, List, Optional, Set, Any
from fastapi import WebSocket, WebSocketDisconnect

class PTYSession:
    def __init__(self, session_id: str, cwd: str, env: Dict[str, str], cols: int = 80, rows: int = 24,
                 project_id: Optional[str] = None, task_id: Optional[str] = None,
                 role: str = "orchestrator", name: Optional[str] = None,
                 agent_type: str = "bash", agent_name: Optional[str] = None,
                 slice_id: Optional[str] = None, log_path: Optional[str] = None,
                 lazy: bool = False):
        self.session_id = session_id
        self.project_id = project_id
        self.task_id = task_id
        self.role = role or "orchestrator"
        self.name = name or ("Orquestrador Staff" if self.role == "orchestrator" else "Terminal")
        self.agent_type = agent_type or "bash"
        self.agent_name = agent_name
        self.slice_id = slice_id or task_id
        self.cwd = cwd if (cwd and os.path.isdir(cwd)) else os.getcwd()
        self.env = env
        self.cols = cols
        self.rows = rows
        self.lazy = lazy
        self.created_at = time.time()
        self.last_active = time.time()
        self.history = deque(maxlen=4000)
        self.active_websockets: Set[WebSocket] = set()
        self.is_alive = False
        self.is_spawned = False
        self.pid: Optional[int] = None
        self.master_fd: Optional[int] = None
        self.slave_fd: Optional[int] = None
        self.reader_task: Optional[asyncio.Task] = None
        self.log_path = log_path

        # Se houver log salvo anteriormente, carrega o buffer prévio do disco
        if self.log_path and os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    max_read = 512 * 1024  # Últimos 512KB
                    if size > max_read:
                        f.seek(size - max_read)
                    else:
                        f.seek(0)
                    saved = f.read()
                    if saved:
                        self.history.append(saved)
                        self.history.append("\r\n\x1b[36m─── [Sessão restaurada após reinicialização - histórico preservado] ───\x1b[0m\r\n")
            except Exception:
                pass

        if not self.lazy:
            self.spawn()

    def spawn(self):
        """Bifurca o processo da shell sob demanda se ainda não estiver instanciado."""
        if self.is_spawned and self.is_alive:
            return

        self.master_fd, self.slave_fd = os.openpty()
        self._set_winsize(self.cols, self.rows)

        self.pid = os.fork()
        if self.pid == 0:
            # Processo Filho (Shell)
            os.close(self.master_fd)
            os.setsid()
            os.dup2(self.slave_fd, 0)
            os.dup2(self.slave_fd, 1)
            os.dup2(self.slave_fd, 2)
            if self.slave_fd > 2:
                os.close(self.slave_fd)
            try:
                os.chdir(self.cwd)
            except Exception:
                pass
            shell = self.env.get("SHELL", "/bin/bash")
            try:
                import ctypes
                libc = ctypes.CDLL("libc.so.6")
                PR_SET_PDEATHSIG = 1
                libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
            except Exception:
                pass
            os.execvpe(shell, [shell], self.env)
        else:
            # Processo Pai
            os.close(self.slave_fd)
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            self.is_alive = True
            self.is_spawned = True
            self.reader_task = None
            try:
                from server.process_lifecycle import get_process_lifecycle_manager
                get_process_lifecycle_manager().register_process(self.pid, name=f"pty:{self.session_id}")
            except Exception:
                pass

    def _set_winsize(self, cols: int, rows: int):
        self.cols = cols
        self.rows = rows
        if self.master_fd is not None:
            try:
                winsize = struct.pack("HHHH", int(rows), int(cols), 0, 0)
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            except Exception:
                pass

    def resize(self, cols: int, rows: int):
        self._set_winsize(cols, rows)

    def write(self, data: str):
        if not self.is_spawned:
            self.spawn()
        if self.is_alive and self.master_fd is not None:
            try:
                os.write(self.master_fd, data.encode("utf-8"))
            except Exception:
                pass

    async def start_reader_if_needed(self):
        if not self.is_spawned:
            self.spawn()
        if self.reader_task is None or self.reader_task.done():
            self.reader_task = asyncio.create_task(self._async_read_loop())

    async def _async_read_loop(self):
        while self.is_alive and self.master_fd is not None:
            await asyncio.sleep(0.015)
            try:
                data = os.read(self.master_fd, 4096)
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                self.history.append(text)
                self.last_active = time.time()

                if self.log_path:
                    try:
                        with open(self.log_path, "a", encoding="utf-8") as lf:
                            lf.write(text)
                    except Exception:
                        pass

                disconnected = []
                for ws in list(self.active_websockets):
                    try:
                        await ws.send_text(text)
                    except Exception:
                        disconnected.append(ws)
                for ws in disconnected:
                    self.detach(ws)
            except (BlockingIOError, InterruptedError):
                continue
            except OSError:
                break
            except Exception:
                continue

        self.close()

    def attach(self, websocket: WebSocket) -> str:
        if not self.is_spawned:
            self.spawn()
        self.active_websockets.add(websocket)
        return "".join(self.history)

    def detach(self, websocket: WebSocket):
        if websocket in self.active_websockets:
            self.active_websockets.remove(websocket)

    def close(self):
        """Encerra o descritor PTY e realiza reaping robusto do processo filho para evitar zombies."""
        if not self.is_alive and not self.is_spawned:
            return
        self.is_alive = False
        self.is_spawned = False
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except Exception:
                pass
            self.master_fd = None

        if self.pid is not None:
            pid = self.pid
            try:
                try:
                    pgid = os.getpgid(pid)
                    if pgid == pid:
                        os.killpg(pgid, signal.SIGTERM)
                except Exception:
                    pass
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                self.pid = None
                return
            except Exception:
                pass

            # Loop não-bloqueante de espera para coleta graciosa
            reaped = False
            for _ in range(5):
                try:
                    wpid, status = os.waitpid(pid, os.WNOHANG)
                    if wpid == pid:
                        reaped = True
                        break
                except (ChildProcessError, ProcessLookupError):
                    reaped = True
                    break
                except Exception:
                    pass
                time.sleep(0.05)

            # Fallback escalonando para SIGKILL caso o processo ainda esteja ativo
            if not reaped:
                try:
                    try:
                        pgid = os.getpgid(pid)
                        if pgid == pid:
                            os.killpg(pgid, signal.SIGKILL)
                    except Exception:
                        pass
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    reaped = True
                except Exception:
                    pass

                for _ in range(5):
                    try:
                        wpid, status = os.waitpid(pid, os.WNOHANG)
                        if wpid == pid:
                            reaped = True
                            break
                    except (ChildProcessError, ProcessLookupError):
                        reaped = True
                        break
                    except Exception:
                        pass
                    time.sleep(0.02)

            try:
                from server.process_lifecycle import get_process_lifecycle_manager
                get_process_lifecycle_manager().unregister_process(pid)
            except Exception:
                pass

            self.pid = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "role": self.role,
            "name": self.name,
            "agent_type": self.agent_type,
            "agent_name": self.agent_name,
            "slice_id": self.slice_id,
            "cwd": self.cwd,
            "pid": self.pid,
            "cols": self.cols,
            "rows": self.rows,
            "is_alive": self.is_alive,
            "is_spawned": self.is_spawned,
            "created_at": self.created_at,
            "last_active": getattr(self, "last_active", self.created_at),
            "active_clients": len(self.active_websockets)
        }


class PTYSessionManager:
    def __init__(self, sessions_dir: Optional[str] = None):
        self._sessions: Dict[str, PTYSession] = {}
        if not sessions_dir:
            base_states = os.getenv("COCKPIT_STATES_DIR") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "states")
            self.sessions_dir = os.getenv("COCKPIT_TERMINALS_DIR") or os.path.join(base_states, "terminals")
        else:
            self.sessions_dir = os.path.abspath(sessions_dir)
        try:
            os.makedirs(self.sessions_dir, exist_ok=True)
        except Exception:
            pass
        self.index_file = os.path.join(self.sessions_dir, "sessions.json")
        self._load_persisted_sessions()

    def _get_log_path(self, session_id: str) -> str:
        safe_id = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in session_id)
        return os.path.join(self.sessions_dir, f"{safe_id}.log")

    def _save_index(self):
        try:
            data = {}
            for s in self._sessions.values():
                data[s.session_id] = {
                    "session_id": s.session_id,
                    "project_id": s.project_id,
                    "task_id": s.task_id,
                    "role": s.role,
                    "name": s.name,
                    "agent_type": s.agent_type,
                    "agent_name": s.agent_name,
                    "slice_id": s.slice_id,
                    "cwd": s.cwd,
                    "cols": s.cols,
                    "rows": s.rows,
                    "created_at": s.created_at,
                    "last_active": getattr(s, "last_active", s.created_at)
                }
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[PTYSessionManager] Erro salvando sessions.json: {e}", file=sys.stderr)

    def _load_persisted_sessions(self):
        if not os.path.isfile(self.index_file):
            return
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            env = self._prepare_env()
            for sid, meta in data.items():
                if not isinstance(meta, dict):
                    continue
                cwd = meta.get("cwd")
                if not cwd or not os.path.isdir(cwd):
                    cwd = os.getcwd()
                log_path = self._get_log_path(sid)
                try:
                    session = PTYSession(
                        session_id=sid,
                        cwd=cwd,
                        env=env,
                        cols=meta.get("cols", 80),
                        rows=meta.get("rows", 24),
                        project_id=meta.get("project_id"),
                        task_id=meta.get("task_id"),
                        role=meta.get("role", "orchestrator"),
                        name=meta.get("name"),
                        agent_type=meta.get("agent_type", "bash"),
                        agent_name=meta.get("agent_name"),
                        slice_id=meta.get("slice_id"),
                        log_path=log_path,
                        lazy=True
                    )
                    session.created_at = meta.get("created_at", time.time())
                    session.last_active = meta.get("last_active", time.time())
                    self._sessions[sid] = session
                except Exception as e:
                    print(f"[PTYSessionManager] Falha ao restaurar sessão persistida {sid}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[PTYSessionManager] Erro lendo sessions.json: {e}", file=sys.stderr)

    def _prepare_env(self) -> Dict[str, str]:
        env = dict(os.environ)
        home = os.path.expanduser("~")
        nvm_bin = os.path.join(home, ".nvm", "versions", "node")
        if os.path.isdir(nvm_bin):
            extra_paths = [os.path.join(nvm_bin, v, "bin") for v in os.listdir(nvm_bin)]
            env["PATH"] = ":".join(extra_paths) + ":" + env.get("PATH", "")
            
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        env["AGENT_COCKPIT_PTY"] = "1"
        env["COCKPIT_PTY_SESSION"] = "1"
        return env

    def get_or_create(self, session_id: str, cwd: Optional[str] = None, cols: int = 80, rows: int = 24,
                      project_id: Optional[str] = None, task_id: Optional[str] = None,
                      role: str = "orchestrator", name: Optional[str] = None,
                      agent_type: str = "bash", agent_name: Optional[str] = None,
                      slice_id: Optional[str] = None, lazy: bool = False) -> PTYSession:
        session = self._sessions.get(session_id)
        if session and session.is_alive:
            if project_id and not session.project_id:
                session.project_id = project_id
            if task_id and not session.task_id:
                session.task_id = task_id
            if role and getattr(session, 'role', None) != role:
                session.role = role
            if name and not getattr(session, 'name', None):
                session.name = name
            if agent_type and not getattr(session, 'agent_type', None):
                session.agent_type = agent_type
            if agent_name and not getattr(session, 'agent_name', None):
                session.agent_name = agent_name
            if slice_id and not getattr(session, 'slice_id', None):
                session.slice_id = slice_id
            self._save_index()
            return session

        if session and not session.is_alive:
            session.close()
            del self._sessions[session_id]

        env = self._prepare_env()
        log_path = self._get_log_path(session_id)
        new_session = PTYSession(
            session_id=session_id, cwd=cwd, env=env, cols=cols, rows=rows,
            project_id=project_id, task_id=task_id,
            role=role, name=name, agent_type=agent_type,
            agent_name=agent_name, slice_id=slice_id, log_path=log_path,
            lazy=lazy
        )
        self._sessions[session_id] = new_session
        self._save_index()
        return new_session

    def get_sessions_by_context(self, project_id: Optional[str] = None, task_id: Optional[str] = None,
                                role: Optional[str] = None) -> List[PTYSession]:
        result = []
        for s in self._sessions.values():
            if not s.is_alive:
                continue
            if project_id and s.project_id != project_id:
                continue
            if task_id and s.task_id != task_id:
                continue
            if role and getattr(s, 'role', None) != role:
                continue
            result.append(s)
        return result

    def get_session(self, session_id: str) -> Optional[PTYSession]:
        return self._sessions.get(session_id)

    def close_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session:
            session.close()
            del self._sessions[session_id]
            self._save_index()
            log_path = self._get_log_path(session_id)
            if os.path.exists(log_path):
                try:
                    os.remove(log_path)
                except Exception:
                    pass
            return True
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if session_id in data:
                    del data[session_id]
                    with open(self.index_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    log_path = self._get_log_path(session_id)
                    if os.path.exists(log_path):
                        os.remove(log_path)
                    return True
            except Exception:
                pass
        return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        dead = [k for k, v in self._sessions.items() if not v.is_alive]
        for k in dead:
            self._sessions[k].close()
            del self._sessions[k]
        self._save_index()
        return [v.to_dict() for v in self._sessions.values()]

    def stop_all(self):
        """Encerra os processos PTY em memória mantendo a persistência em disco intacta (ex: shutdown do servidor)."""
        for s in list(self._sessions.values()):
            s.close()
        self._sessions.clear()

    def cleanup_all(self):
        """Limpeza completa para testes (encerra processos e remove arquivos de estado)."""
        for s in list(self._sessions.values()):
            s.close()
        self._sessions.clear()
        if os.path.exists(self.index_file):
            try:
                os.remove(self.index_file)
            except Exception:
                pass

pty_session_manager = PTYSessionManager()

