"""
LocalWorkerQueue: Fila FIFO coordenada para execução sequencial de inferência no Local LLM (Ollama).
Garante acesso exclusivo à GPU, status em tempo real para os subagentes e notificação síncrona/reativa.
Suporta persistência atômica com locks inter-processos para sincronização entre MCP e Web Server.
"""

import os
import sys
import time
import json
import uuid
import tempfile
import threading
from contextlib import contextmanager
from typing import Dict, List, Any, Optional, Callable

try:
    import fcntl
except ImportError:
    fcntl = None

DEFAULT_SNAPSHOT_PATH = os.path.join("states", "worker_queue.json")


class LocalWorkerQueue:
    def __init__(self, max_history: int = 50, snapshot_path: Optional[str] = None):
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self.condition = self._condition  # Exposição pública para verificação e sincronização
        
        self._explicit_snapshot_path = snapshot_path

        # Fila FIFO de tarefas aguardando
        self._waiting_queue: List[Dict[str, Any]] = []
        
        # Tarefa em processamento na GPU (ou None se livre)
        self._active_task: Optional[Dict[str, Any]] = None
        
        # Histórico de tarefas finalizadas
        self._history: List[Dict[str, Any]] = []
        self._max_history = max_history
        
        # Mapa indexado de todos os tickets para consulta rápida
        self._tickets: Dict[str, Dict[str, Any]] = {}
        
        # Callbacks registrados para notificações de alteração de estado
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []

    @property
    def snapshot_path(self) -> str:
        """Resolve o caminho do arquivo de snapshot dinamicamente."""
        if self._explicit_snapshot_path:
            return self._explicit_snapshot_path
        # Verifica nos módulos conhecidos no sys.modules para permitir mock/patch consistente
        for mod_name in ("server.workers.worker_queue", "workers.worker_queue", __name__):
            mod = sys.modules.get(mod_name)
            if mod and hasattr(mod, "DEFAULT_SNAPSHOT_PATH"):
                val = getattr(mod, "DEFAULT_SNAPSHOT_PATH")
                if val != DEFAULT_SNAPSHOT_PATH:
                    return val
        mod = sys.modules.get(__name__)
        if mod and hasattr(mod, "DEFAULT_SNAPSHOT_PATH"):
            return getattr(mod, "DEFAULT_SNAPSHOT_PATH")
        return DEFAULT_SNAPSHOT_PATH

    @contextmanager
    def _file_lock(self, filepath: str):
        """Context manager de lock de arquivo usando fcntl.flock para exclusão mútua inter-processos."""
        lock_path = filepath + ".lock"
        lock_dir = os.path.dirname(os.path.abspath(lock_path))
        if lock_dir:
            os.makedirs(lock_dir, exist_ok=True)
        fd = None
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
            if fcntl:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                except (OSError, IOError):
                    pass
            yield
        finally:
            if fd is not None:
                if fcntl:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    except (OSError, IOError):
                        pass
                try:
                    os.close(fd)
                except Exception:
                    pass

    def _atomic_write_json(self, filepath: str, data: Any) -> None:
        """Grava JSON de forma atômica criando arquivo temporário no mesmo diretório e aplicando os.replace."""
        target_dir = os.path.dirname(os.path.abspath(filepath))
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)
        with self._file_lock(filepath):
            temp_fd, temp_path = tempfile.mkstemp(dir=target_dir or ".", prefix=".tmp_wq_", suffix=".tmp")
            try:
                with open(temp_fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, filepath)
            except Exception:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
                raise

    def save_snapshot(self, filepath: Optional[str] = None) -> None:
        """Salva snapshot atômico do estado atual da fila em arquivo compartilhado com lock."""
        target_path = filepath or self.snapshot_path
        with self._lock:
            snapshot = self._build_status_unlocked()
            snapshot["_waiting_queue"] = list(self._waiting_queue)
            snapshot["_active_task"] = dict(self._active_task) if self._active_task else None
            snapshot["_tickets"] = dict(self._tickets)
            snapshot["_history"] = list(self._history)
            snapshot["timestamp"] = time.time()
        self._atomic_write_json(target_path, snapshot)

    def load_snapshot(self, filepath: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Carrega snapshot salvo em arquivo compartilhado e sincroniza o estado interno."""
        target_path = filepath or self.snapshot_path
        if not os.path.exists(target_path):
            return None
        with self._file_lock(target_path):
            try:
                with open(target_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                return None

        with self._lock:
            if "_waiting_queue" in data:
                self._waiting_queue = data.get("_waiting_queue", [])
            elif "queued_tasks" in data:
                self._waiting_queue = [
                    {k: v for k, v in t.items() if k not in ("position", "waiting_seconds")}
                    for t in data.get("queued_tasks", [])
                ]

            if "_active_task" in data:
                self._active_task = data.get("_active_task")
            elif "active_task" in data:
                self._active_task = data.get("active_task")

            if "_tickets" in data:
                self._tickets = data.get("_tickets", {})
            else:
                self._tickets = {}
                if self._active_task:
                    tid = self._active_task.get("ticket_id")
                    if tid:
                        self._tickets[tid] = self._active_task
                for t in self._waiting_queue:
                    tid = t.get("ticket_id")
                    if tid:
                        self._tickets[tid] = t

            if "_history" in data:
                self._history = data.get("_history", [])
            elif "history" in data:
                self._history = data.get("history", [])

        return data

    def register_listener(self, listener: Callable[[Dict[str, Any]], None]) -> None:
        """Registra um callback a ser acionado sempre que o estado da fila mudar."""
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def unregister_listener(self, listener: Callable[[Dict[str, Any]], None]) -> None:
        """Remove um callback de notificação."""
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def _notify_listeners_unlocked(self) -> None:
        """Dispara callbacks de notificação sem reter o lock durante a invocação externa."""
        status = self.get_queue_status()
        listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(status)
            except Exception:
                pass

    def enqueue(self, slice_id: str, target_file: str, instruction_summary: str = "") -> str:
        """
        Enfileira uma nova tarefa para o Local Worker.
        Invoque self._condition.notify_all() sob o lock e salva o snapshot compartilhado.
        Retorna o ticket_id gerado.
        """
        ticket_id = f"ticket-{uuid.uuid4().hex[:8]}"
        now = time.time()

        task_data = {
            "ticket_id": ticket_id,
            "slice_id": slice_id,
            "target_file": target_file,
            "instruction_summary": (instruction_summary or "")[:150],
            "status": "queued",
            "enqueued_at": now,
            "started_at": None,
            "completed_at": None,
            "tokens": 0,
            "duration": 0.0,
            "error": None
        }

        with self._condition:
            self._waiting_queue.append(task_data)
            self._tickets[ticket_id] = task_data
            self._condition.notify_all()
            self.save_snapshot()
            self._notify_listeners_unlocked()

        return ticket_id

    def get_job(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Aguarda até que haja pelo menos uma tarefa na fila de espera e a retorna (ou None em timeout).
        Acorda imediatamente ao ser notificada por enqueue() via self._condition.notify_all().
        """
        start_time = time.time()
        with self._condition:
            while not self._waiting_queue:
                if timeout is not None:
                    elapsed = time.time() - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        return None
                    self._condition.wait(remaining)
                else:
                    self._condition.wait()
            return dict(self._waiting_queue[0])

    def acquire_worker(self, ticket_id: str, timeout: Optional[float] = 300.0) -> bool:
        """
        Aguarda até que seja a vez estrita do ticket (FIFO) e que a GPU esteja livre.
        Retorna True se adquiriu o worker com sucesso, ou False em caso de timeout/cancelamento.
        """
        start_time = time.time()

        with self._condition:
            if ticket_id not in self._tickets:
                return False

            while True:
                # Condição de aquisição: worker livre E ticket é o primeiro da fila FIFO
                if self._active_task is None and self._waiting_queue and self._waiting_queue[0]["ticket_id"] == ticket_id:
                    # Adquire a GPU
                    task = self._waiting_queue.pop(0)
                    task["status"] = "running"
                    task["started_at"] = time.time()
                    self._active_task = task
                    self.save_snapshot()
                    self._notify_listeners_unlocked()
                    return True

                # Calcula timeout restante se especificado
                if timeout is not None:
                    elapsed = time.time() - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        # Timeout esgotado: remove da fila e marca como timeout
                        if any(t["ticket_id"] == ticket_id for t in self._waiting_queue):
                            self._waiting_queue = [t for t in self._waiting_queue if t["ticket_id"] != ticket_id]
                        ticket = self._tickets.get(ticket_id)
                        if ticket:
                            ticket["status"] = "timeout"
                            ticket["completed_at"] = time.time()
                        self.save_snapshot()
                        self._notify_listeners_unlocked()
                        return False
                    self._condition.wait(remaining)
                else:
                    self._condition.wait()

    def release_worker(
        self,
        ticket_id: str,
        status: str = "completed",
        tokens: int = 0,
        duration: float = 0.0,
        error: Optional[str] = None
    ) -> None:
        """
        Libera o worker após o término da tarefa (sucesso ou erro),
        atualiza o histórico, persiste snapshot e acorda a próxima tarefa na fila.
        """
        with self._condition:
            # Se for a tarefa ativa
            if self._active_task and self._active_task.get("ticket_id") == ticket_id:
                finished_task = self._active_task
                finished_task["status"] = status
                finished_task["completed_at"] = time.time()
                finished_task["tokens"] = tokens
                finished_task["duration"] = duration
                if error:
                    finished_task["error"] = error

                self._history.insert(0, dict(finished_task))
                if len(self._history) > self._max_history:
                    self._history.pop()

                self._active_task = None
            elif ticket_id in self._tickets:
                # Caso o ticket estivesse na fila de espera e tenha sido cancelado/liberado
                self._waiting_queue = [t for t in self._waiting_queue if t["ticket_id"] != ticket_id]
                ticket = self._tickets[ticket_id]
                ticket["status"] = status
                ticket["completed_at"] = time.time()
                ticket["error"] = error
                self._history.insert(0, dict(ticket))

            # Notifica todas as threads aguardando na condição
            self._condition.notify_all()
            self.save_snapshot()
            self._notify_listeners_unlocked()

    def get_ticket_status(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Retorna as informações e posição detalhada de um ticket específico."""
        target_path = self.snapshot_path
        if os.path.exists(target_path):
            self.load_snapshot(target_path)

        with self._lock:
            ticket = self._tickets.get(ticket_id)
            if not ticket:
                return None

            data = dict(ticket)
            if self._active_task and self._active_task.get("ticket_id") == ticket_id:
                data["position"] = 0
                data["is_active"] = True
            else:
                pos = None
                for idx, t in enumerate(self._waiting_queue):
                    if t["ticket_id"] == ticket_id:
                        pos = idx + 1
                        break
                data["position"] = pos
                data["is_active"] = False

            return data

    def get_queue_status(
        self,
        slice_id: Optional[str] = None,
        ticket_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retorna o estado global da fila do Local Worker com cálculo opcional da posição
        e mensagem contextual em PT-BR para um slice_id ou ticket_id.
        Sincroniza automaticamente a partir do snapshot compartilhado se existir.
        """
        target_path = self.snapshot_path
        if os.path.exists(target_path):
            self.load_snapshot(target_path)

        with self._lock:
            status = self._build_status_unlocked()

        # Determina a posição da fatia/ticket solicitado
        target_pos = None
        target_ticket = None

        if ticket_id or slice_id:
            if status["active_task"] and (
                (ticket_id and status["active_task"].get("ticket_id") == ticket_id) or
                (slice_id and status["active_task"].get("slice_id") == slice_id)
            ):
                target_pos = 0
                target_ticket = status["active_task"]
            else:
                for t in status["queued_tasks"]:
                    if (ticket_id and t.get("ticket_id") == ticket_id) or (slice_id and t.get("slice_id") == slice_id):
                        target_pos = t.get("position")
                        target_ticket = t
                        break

        status["your_position"] = target_pos
        status["message"] = self._format_ptbr_message(status, target_pos, target_ticket)
        return status

    def _build_status_unlocked(self) -> Dict[str, Any]:
        """Monta o snapshot do status da fila (deve ser chamado com self._lock retido)."""
        is_busy = self._active_task is not None
        active = dict(self._active_task) if self._active_task else None
        
        # Adiciona tempo de execução decorrido se ativo
        if active and active.get("started_at"):
            active["elapsed_seconds"] = round(time.time() - active["started_at"], 1)

        queued_list = []
        for idx, task in enumerate(self._waiting_queue):
            item = dict(task)
            item["position"] = idx + 1
            item["waiting_seconds"] = round(time.time() - item.get("enqueued_at", time.time()), 1)
            queued_list.append(item)

        return {
            "is_busy": is_busy,
            "active_task": active,
            "queue_length": len(self._waiting_queue),
            "queued_tasks": queued_list,
            "history": list(self._history[:10])
        }

    def _format_ptbr_message(
        self,
        status: Dict[str, Any],
        target_pos: Optional[int],
        target_ticket: Optional[Dict[str, Any]]
    ) -> str:
        """Gera mensagem explicativa e amigável em PT-BR."""
        active = status.get("active_task")
        queue_len = status.get("queue_length", 0)

        if target_pos == 0:
            return f"Sua tarefa está atualmente em execução na GPU (Fatia: {active.get('slice_id')})."
        elif target_pos is not None and target_pos > 0:
            active_info = f" A GPU está processando a fatia '{active.get('slice_id')} ({active.get('target_file')})'." if active else ""
            return f"Você é o {target_pos}º na fila de espera (total na fila: {queue_len}).{active_info} Aguarde sua vez."
        elif status.get("is_busy"):
            return f"A GPU está ocupada processando a fatia '{active.get('slice_id')}'. {queue_len} tarefa(s) aguardando na fila."
        elif queue_len > 0:
            return f"Existem {queue_len} tarefa(s) na fila aguardando início."
        else:
            return "A GPU do Local Worker está livre e pronta para receber requisições."


# Instância global singleton acessível por todo o servidor
local_worker_queue = LocalWorkerQueue()
