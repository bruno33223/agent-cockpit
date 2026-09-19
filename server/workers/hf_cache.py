"""
Módulo de Cache Offline e Persistência para o Hugging Face Hub.
Implementa cache em dois níveis:
1. Cache em memória (RAM) com TTL (Time-To-Live).
2. Cache persistido em disco com escrita atômica para fallback offline e resiliência a falhas de rede.
Thread-safe e tolerante a arquivos corrompidos.
"""

import copy
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hf_cache")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STATES_DIR = os.getenv("COCKPIT_STATES_DIR") or os.path.join(BASE_DIR, "states")
DEFAULT_CACHE_DIR = os.path.join(STATES_DIR, "cache")
DEFAULT_CACHE_FILE = os.getenv("COCKPIT_HF_CACHE_FILE") or os.path.join(DEFAULT_CACHE_DIR, "hf_models_cache.json")


class HFModelCache:
    """
    Gerenciador de cache thread-safe em memória e disco para metadados de modelos Hugging Face.
    """

    def __init__(
        self,
        cache_file: Optional[str] = None,
        default_ttl: float = 3600.0
    ):
        self.cache_file = os.path.abspath(cache_file) if cache_file else DEFAULT_CACHE_FILE
        self.default_ttl = float(default_ttl)
        self._lock = threading.RLock()
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._disk_cache: Dict[str, Dict[str, Any]] = {}

        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Carrega o cache persistido do disco na tabela _disk_cache (sem poluir a memória volátil ativa)."""
        with self._lock:
            if not os.path.exists(self.cache_file):
                return
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        return
                    data = json.loads(content)

                if isinstance(data, dict):
                    entries = data.get("query_cache", data)
                    if isinstance(entries, dict):
                        for k, v in entries.items():
                            if isinstance(v, dict) and "models" in v and isinstance(v["models"], list):
                                self._disk_cache[k] = v
            except Exception as exc:
                logger.warning(
                    "Falha ao ler cache persistido em %s (%s). O arquivo será ignorado ou recriado.",
                    self.cache_file,
                    exc
                )

    def _save_to_disk(self) -> None:
        """Salva atomicamente o cache no disco para evitar corrupção por escrita concorrente ou falha abrupta."""
        with self._lock:
            try:
                cache_dir = os.path.dirname(self.cache_file)
                if cache_dir:
                    os.makedirs(cache_dir, exist_ok=True)

                tmp_path = f"{self.cache_file}.tmp.{os.getpid()}.{threading.get_ident()}"
                payload = {
                    "version": 1,
                    "updated_at": time.time(),
                    "query_cache": self._disk_cache
                }

                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)

                os.replace(tmp_path, self.cache_file)
            except Exception as exc:
                logger.warning("Falha ao salvar cache persistido em %s: %s", self.cache_file, exc)
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass

    def get(self, key: str, max_age: Optional[float] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Retorna os modelos cacheados se estiverem dentro do TTL em memória.
        Retorna None em caso de cache miss ou expiração.
        """
        ttl = float(max_age) if max_age is not None else self.default_ttl
        with self._lock:
            entry = self._memory_cache.get(key)
            if entry and isinstance(entry, dict):
                ts = float(entry.get("timestamp", 0))
                if time.time() - ts <= ttl:
                    models = entry.get("models")
                    if isinstance(models, list):
                        return copy.deepcopy(models)
            return None

    def get_stale_or_disk(self, key: str) -> Optional[List[Dict[str, Any]]]:
        """
        Retorna dados de fallback (memória expirada ou disco) quando a rede está inacessível.
        Retorna None se não houver dados registrados.
        """
        with self._lock:
            # 1. Tenta memória mesmo se expirado
            entry = self._memory_cache.get(key)
            if entry and isinstance(entry, dict):
                models = entry.get("models")
                if isinstance(models, list) and len(models) > 0:
                    return copy.deepcopy(models)

            # 2. Tenta recarregar do disco se disponível
            if key not in self._disk_cache:
                self._load_from_disk()

            entry = self._disk_cache.get(key)
            if entry and isinstance(entry, dict):
                models = entry.get("models")
                if isinstance(models, list) and len(models) > 0:
                    return copy.deepcopy(models)

            return None

    def set(self, key: str, models: List[Dict[str, Any]], persist: bool = True) -> None:
        """Armazena modelos na memória e persiste no disco."""
        with self._lock:
            now = time.time()
            data_entry = {
                "timestamp": now,
                "models": copy.deepcopy(models)
            }
            self._memory_cache[key] = data_entry
            self._disk_cache[key] = data_entry
            if persist:
                self._save_to_disk()

    def clear(self) -> None:
        """Limpa o cache em memória e o arquivo em disco."""
        with self._lock:
            self._memory_cache.clear()
            self._disk_cache.clear()
            if os.path.exists(self.cache_file):
                try:
                    os.remove(self.cache_file)
                except Exception:
                    pass


# Singleton padrão para compartilhamento em todo o processo
_global_hf_cache: Optional[HFModelCache] = None
_global_cache_lock = threading.Lock()


def get_default_hf_cache() -> HFModelCache:
    """Retorna ou cria o singleton padrão de cache HF."""
    global _global_hf_cache
    if _global_hf_cache is None:
        with _global_cache_lock:
            if _global_hf_cache is None:
                _global_hf_cache = HFModelCache()
    return _global_hf_cache
