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
    def __init__(self, session_id: str, cwd: str, env: Dict[str, str], cols: int = 80, rows: int = 24):
        self.session_id = session_id
        self.cwd = cwd if (cwd and os.path.isdir(cwd)) else os.getcwd()
        self.env = env
        self.cols = cols
        self.rows = rows
        self.created_at = time.time()
        self.history = deque(maxlen=4000)
        self.active_websockets: Set[WebSocket] = set()
        self.is_alive = False

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
            os.execvpe(shell, [shell], self.env)
        else:
            # Processo Pai
            os.close(self.slave_fd)
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            self.is_alive = True
            self.reader_task: Optional[asyncio.Task] = None

    def _set_winsize(self, cols: int, rows: int):
        try:
            winsize = struct.pack("HHHH", int(rows), int(cols), 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            self.cols = cols
            self.rows = rows
        except Exception:
            pass

    def resize(self, cols: int, rows: int):
        self._set_winsize(cols, rows)

    def write(self, data: str):
        if self.is_alive:
            try:
                os.write(self.master_fd, data.encode("utf-8"))
            except Exception:
                pass

    async def start_reader_if_needed(self):
        if self.reader_task is None or self.reader_task.done():
            self.reader_task = asyncio.create_task(self._async_read_loop())

    async def _async_read_loop(self):
        while self.is_alive:
            await asyncio.sleep(0.015)
            try:
                data = os.read(self.master_fd, 4096)
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                self.history.append(text)

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
        self.active_websockets.add(websocket)
        return "".join(self.history)

    def detach(self, websocket: WebSocket):
        if websocket in self.active_websockets:
            self.active_websockets.remove(websocket)

    def close(self):
        if not self.is_alive:
            return
        self.is_alive = False
        try:
            os.close(self.master_fd)
        except Exception:
            pass
        try:
            os.kill(self.pid, signal.SIGTERM)
            os.waitpid(self.pid, os.WNOHANG)
        except Exception:
            pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "pid": self.pid,
            "cols": self.cols,
            "rows": self.rows,
            "is_alive": self.is_alive,
            "created_at": self.created_at,
            "active_clients": len(self.active_websockets)
        }


class PTYSessionManager:
    def __init__(self):
        self._sessions: Dict[str, PTYSession] = {}

    def _prepare_env(self) -> Dict[str, str]:
        env = dict(os.environ)
        home = os.path.expanduser("~")
        nvm_bin = os.path.join(home, ".nvm", "versions", "node")
        if os.path.isdir(nvm_bin):
            extra_paths = [os.path.join(nvm_bin, v, "bin") for v in os.listdir(nvm_bin)]
            env["PATH"] = ":".join(extra_paths) + ":" + env.get("PATH", "")
            
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        return env

    def get_or_create(self, session_id: str, cwd: Optional[str] = None, cols: int = 80, rows: int = 24) -> PTYSession:
        session = self._sessions.get(session_id)
        if session and session.is_alive:
            return session

        if session and not session.is_alive:
            session.close()
            del self._sessions[session_id]

        env = self._prepare_env()
        new_session = PTYSession(session_id=session_id, cwd=cwd, env=env, cols=cols, rows=rows)
        self._sessions[session_id] = new_session
        return new_session

    def get_session(self, session_id: str) -> Optional[PTYSession]:
        return self._sessions.get(session_id)

    def close_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session:
            session.close()
            del self._sessions[session_id]
            return True
        return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        dead = [k for k, v in self._sessions.items() if not v.is_alive]
        for k in dead:
            self._sessions[k].close()
            del self._sessions[k]
        return [v.to_dict() for v in self._sessions.values()]

    def cleanup_all(self):
        for s in self._sessions.values():
            s.close()
        self._sessions.clear()

pty_session_manager = PTYSessionManager()
