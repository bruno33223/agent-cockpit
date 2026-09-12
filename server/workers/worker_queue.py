"""
LocalWorkerQueue: Fila FIFO coordenada para execução sequencial de inferência no Local LLM (Ollama).
Garante acesso exclusivo à GPU, status em tempo real para os subagentes e notificação síncrona/reativa.
"""

import time
import uuid
import threading
from typing import Dict, List, Any, Optional, Callable


class LocalWorkerQueue:
    def __init__(self, max_history: int = 50):
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        
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
            self._notify_listeners_unlocked()

        return ticket_id

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
        atualiza o histórico e acorda a próxima tarefa na fila.
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
            self._notify_listeners_unlocked()

    def get_ticket_status(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Retorna as informações e posição detalhada de um ticket específico."""
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
        """
        with self._lock:
            status = self._build_status_unlocked()

        # Determina a posição da fatia/ticket solicitado
        target_pos = None
        target_ticket = None

        if ticket_id or slice_id:
            if status["active_task"] and (
                (ticket_id and status["active_task"]["ticket_id"] == ticket_id) or
                (slice_id and status["active_task"]["slice_id"] == slice_id)
            ):
                target_pos = 0
                target_ticket = status["active_task"]
            else:
                for t in status["queued_tasks"]:
                    if (ticket_id and t["ticket_id"] == ticket_id) or (slice_id and t["slice_id"] == slice_id):
                        target_pos = t["position"]
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
