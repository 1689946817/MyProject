"""
轻量级进程内内存缓存模块。

提供带 TTL（生存时间）和容量上限的线程安全内存缓存。
适用于缓存检索结果、模型响应等短期热数据，避免重复计算或外部调用。
使用 OrderedDict 实现 LRU（最近最少使用）淘汰策略。
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Generic, Optional, TypeVar

K = TypeVar("K")  # 缓存键的类型
V = TypeVar("V")  # 缓存值的类型


class TTLMemoryCache(Generic[K, V]):
    """带 TTL 和容量上限的最小内存缓存。

    特性：
    - 线程安全：内部使用 RLock 保护所有读写操作
    - TTL 过期：每个条目在写入时记录过期时间，读取时自动淘汰已过期条目
    - 容量限制：超过 max_size 时按 LRU 策略淘汰最久未访问的条目
    - 命中统计：记录 hits/misses 次数，可通过 stats() 获取
    """

    def __init__(self, *, ttl_seconds: float, max_size: int):
        # TTL 为 0 表示永不过期（但仍受容量限制）
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        # 容量至少为 1
        self.max_size = max(1, int(max_size))
        # 使用 OrderedDict 维护访问顺序，值为 (过期时间戳, 实际值) 的元组
        self._items: OrderedDict[K, tuple[float, V]] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0    # 缓存命中次数
        self._misses = 0  # 缓存未命中次数

    def get(self, key: K) -> Optional[V]:
        """获取缓存值。

        若 key 不存在或已过期，返回 None 并计入 misses；
        若命中，将条目移到 OrderedDict 末尾（标记为最近使用）并计入 hits。
        """
        now = time.monotonic()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                self._misses += 1
                return None

            expires_at, value = item
            # 检查是否已过期
            if expires_at < now:
                self._items.pop(key, None)
                self._misses += 1
                return None

            # LRU: 将命中的条目移到末尾
            self._items.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: K, value: V) -> None:
        """写入缓存条目。

        计算过期时间 = 当前时间 + TTL，写入后执行淘汰检查。
        若 key 已存在则更新值和过期时间。
        """
        expires_at = time.monotonic() + self.ttl_seconds
        with self._lock:
            self._items[key] = (expires_at, value)
            self._items.move_to_end(key)
            self._evict_locked()

    def clear(self) -> None:
        """清空所有缓存条目并重置命中统计。"""
        with self._lock:
            self._items.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, int]:
        """返回缓存统计信息。

        先清理过期条目，再返回当前 size、hits、misses。
        """
        with self._lock:
            self._purge_expired_locked()
            return {
                "size": len(self._items),
                "hits": self._hits,
                "misses": self._misses,
            }

    def _evict_locked(self) -> None:
        """执行淘汰：先清理过期条目，再按 LRU 策略淘汰超出容量的条目。"""
        self._purge_expired_locked()
        # popitem(last=False) 移除最久未访问的条目（OrderedDict 头部）
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)

    def _purge_expired_locked(self) -> None:
        """遍历所有条目，移除已过期的条目。"""
        now = time.monotonic()
        expired_keys = [
            key for key, (expires_at, _) in self._items.items()
            if expires_at < now
        ]
        for key in expired_keys:
            self._items.pop(key, None)
