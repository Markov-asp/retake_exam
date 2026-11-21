"""Потокобезопасный TTL-кэш для агрегатов и графиков.

Агрегации по большим отчётам выполняются в SQLite, но повторные запросы
с одинаковыми фильтрами (переключение вкладок, ресайз страницы) не должны
заново пересчитывать те же данные. Кэш живёт в памяти процесса и
сбрасывается при загрузке нового отчёта.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any


def make_key(*parts: Any) -> str:
    """Стабильный ключ кэша из произвольного набора аргументов."""
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


class TTLCache:
    """Небольшой LRU-кэш с временем жизни записей."""

    def __init__(self, ttl_seconds: float = 300.0, max_entries: int = 256) -> None:
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self.max_entries = max(1, int(max_entries))
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self._misses += 1
                return None
            expires_at, value = entry
            if expires_at <= now:
                self._data.pop(key, None)
                self._misses += 1
                return None
            self._data.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        now = time.monotonic()
        with self._lock:
            self._data[key] = (now + self.ttl_seconds, value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def get_or_set(self, key: str, producer: Callable[[], Any]) -> Any:
        """Возвращает значение из кэша или вычисляет и запоминает его."""
        cached = self.get(key)
        if cached is not None:
            return cached
        value = producer()
        if value is not None:
            self.set(key, value)
        return value

    def invalidate(self) -> None:
        """Полностью очищает кэш (вызывается после импорта отчёта)."""
        with self._lock:
            self._data.clear()

    def stats(self) -> dict[str, int | float]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._data),
                "max_entries": self.max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total else 0.0,
                "ttl_seconds": self.ttl_seconds,
            }
