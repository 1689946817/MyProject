"""轻量级进程内内存缓存。"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Generic, Optional, TypeVar


K = TypeVar("K")
V = TypeVar("V")


class TTLMemoryCache(Generic[K, V]):
    """带 TTL 和容量上限的最小内存缓存。"""

    def __init__(self, *, ttl_seconds: float, max_size: int):
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self.max_size = max(1, int(max_size))
        self._items: OrderedDict[K, tuple[float, V]] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: K) -> Optional[V]:
        now = time.monotonic()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                self._misses += 1
                return None

            expires_at, value = item
            if expires_at < now:
                self._items.pop(key, None)
                self._misses += 1
                return None

            self._items.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: K, value: V) -> None:
        expires_at = time.monotonic() + self.ttl_seconds
        with self._lock:
            self._items[key] = (expires_at, value)
            self._items.move_to_end(key)
            self._evict_locked()

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, int]:
        with self._lock:
            self._purge_expired_locked()
            return {
                "size": len(self._items),
                "hits": self._hits,
                "misses": self._misses,
            }

    def _evict_locked(self) -> None:
        self._purge_expired_locked()
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)

    def _purge_expired_locked(self) -> None:
        now = time.monotonic()
        expired_keys = [
            key for key, (expires_at, _) in self._items.items()
            if expires_at < now
        ]
        for key in expired_keys:
            self._items.pop(key, None)
