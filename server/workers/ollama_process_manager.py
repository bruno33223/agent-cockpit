"""
OllamaProcessManager: Gerenciamento do ciclo de vida do processo local Ollama.
Responsável por verificação de binário, portas de rede, inicialização/término gracioso
de subprocesso, buffer circular de logs e broadcast via callbacks.
"""

import os
import shutil
import socket
import subprocess
import threading
from collections import deque
from typing import Dict, List, Any, Optional, Callable


class OllamaProcessManager:
    """
    Controlador do ciclo de vida e monitoramento do processo local Ollama.
    """

    DEFAULT_PORT = 11434
    DEFAULT_HOST = "127.0.0.1"
    STANDARD_BIN_PATHS = [
        "/usr/local/bin/ollama",
        "/usr/bin/ollama",
        os.path.expanduser("~/.local/bin/ollama"),
    ]

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        max_logs: int = 500,
    ):
        self.host = host
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.logs: deque[str] = deque(maxlen=max_logs)
        self._log_callbacks: List[Callable[[str], Any]] = []
        self._reader_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def get_binary_path(self) -> Optional[str]:
        """
        Localiza o executável do Ollama no PATH do sistema ou nos caminhos padrão.
        """
        which_path = shutil.which("ollama")
        if which_path:
            return which_path

        for std_path in self.STANDARD_BIN_PATHS:
            if os.path.exists(std_path):
                return std_path

        return None

    def is_installed(self) -> bool:
        """
        Verifica se o binário do Ollama está disponível no ambiente.
        """
        return self.get_binary_path() is not None

    def is_port_open(
        self,
        port: Optional[int] = None,
        host: Optional[str] = None,
        timeout: float = 1.0,
    ) -> bool:
        """
        Verifica se uma porta de rede TCP está aberta e aceitando conexões.
        """
        target_port = port if port is not None else self.port
        target_host = host if host is not None else self.host

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                return sock.connect_ex((target_host, target_port)) == 0
        except Exception:
            return False

    def add_log_callback(self, callback: Callable[[str], Any]) -> None:
        """
        Registra uma função de callback para receber novas linhas de log em tempo real.
        """
        with self._lock:
            if callback not in self._log_callbacks:
                self._log_callbacks.append(callback)

    def remove_log_callback(self, callback: Callable[[str], Any]) -> None:
        """
        Remove um callback de log previamente registrado.
        """
        with self._lock:
            if callback in self._log_callbacks:
                self._log_callbacks.remove(callback)

    def _append_log(self, line: str) -> None:
        """
        Adiciona uma linha de log ao buffer circular e notifica todos os callbacks.
        """
        with self._lock:
            self.logs.append(line)
            callbacks = list(self._log_callbacks)

        for cb in callbacks:
            try:
                cb(line)
            except Exception:
                # Falha em callback não deve interromper fluxo principal nem a thread de leitura
                pass

    def _stream_logs(self) -> None:
        """
        Thread de leitura contínua do stdout/stderr do processo Ollama.
        """
        proc = self.process
        if not proc or not proc.stdout:
            return

        try:
            for line in proc.stdout:
                clean_line = line.rstrip("\r\n")
                self._append_log(clean_line)
        except Exception as e:
            self._append_log(f"[OllamaProcessManager] Erro no fluxo de logs: {e}")

    def start(self) -> Dict[str, Any]:
        """
        Inicia o servidor Ollama caso não esteja em execução.
        Evita criar processos duplicados se a porta já estiver aberta ou se o
        subprocesso gerenciado já estiver ativo.
        """
        # Se o subprocesso gerenciado já estiver rodando
        if self.process is not None and self.process.poll() is None:
            return {
                "status": "already_running",
                "running": True,
                "managed": True,
                "pid": self.process.pid,
                "port": self.port,
                "message": "Subprocesso Ollama gerenciado já está em execução.",
            }

        # Se a porta já responder (ex: Ollama iniciado externamente via systemd/docker)
        if self.is_port_open(self.port, self.host):
            return {
                "status": "already_running",
                "running": True,
                "managed": False,
                "pid": None,
                "port": self.port,
                "message": f"Ollama já está ouvindo na porta {self.port} (processo externo).",
            }

        bin_path = self.get_binary_path()
        if not bin_path:
            raise RuntimeError(
                "Ollama não encontrado no PATH nem nos caminhos padrão (/usr/local/bin/ollama)."
            )

        self.process = subprocess.Popen(
            [bin_path, "serve"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        self._reader_thread = threading.Thread(target=self._stream_logs, daemon=True)
        self._reader_thread.start()

        return {
            "status": "started",
            "running": True,
            "managed": True,
            "pid": self.process.pid,
            "port": self.port,
            "message": f"Subprocesso Ollama iniciado com PID {self.process.pid}.",
        }

    def stop(self, timeout: float = 5.0) -> Dict[str, Any]:
        """
        Encerra graciosamente o processo Ollama com SIGTERM, aplicando fallback para
        SIGKILL se o processo não responder dentro do tempo limite.
        """
        if self.process is None or self.process.poll() is not None:
            self.process = None
            return {
                "status": "not_running",
                "running": False,
                "message": "Nenhum subprocesso Ollama gerenciado em execução.",
            }

        proc = self.process
        status = "stopped"
        try:
            proc.terminate()
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=timeout)
            status = "killed"
        finally:
            self.process = None

        return {
            "status": status,
            "running": False,
            "message": f"Subprocesso Ollama encerrado com sucesso ({status}).",
        }

    def get_status(self) -> Dict[str, Any]:
        """
        Coleta e retorna o status atual do serviço Ollama e do processo gerenciado.
        """
        installed = self.is_installed()
        port_open = self.is_port_open(self.port, self.host)
        is_managed = self.process is not None and self.process.poll() is None
        running = is_managed or port_open

        return {
            "installed": installed,
            "running": running,
            "managed": is_managed,
            "pid": self.process.pid if is_managed else None,
            "port": self.port,
            "host": self.host,
            "port_open": port_open,
            "logs_count": len(self.logs),
        }

    def get_logs(self, limit: int = 100) -> List[str]:
        """
        Retorna as últimas N linhas do buffer circular de logs.
        """
        with self._lock:
            log_list = list(self.logs)

        if limit <= 0:
            return []
        return log_list[-limit:]
