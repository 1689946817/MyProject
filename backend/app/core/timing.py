"""
轻量级请求耗时采集工具模块。

基于 ContextVar 实现异步安全的请求级耗时追踪。
每个请求创建一个 RequestTimingCollector，通过 contextmanager 记录各阶段耗时，
最终汇总为结构化数据，可用于日志输出或 API 响应中的 timing 字段。

核心概念：
- trace_id: 每个请求的唯一追踪 ID（UUID）
- stage: 请求中的一个处理阶段（如"检索"、"重排"、"生成"）
- first_token_ms: 流式场景下首字输出的延迟
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Iterator, Optional


logger = logging.getLogger(__name__)

# 使用 ContextVar 存储当前协程/线程的计时收集器
# ContextVar 在异步环境下天然安全，不同请求的计时数据互不干扰
_CURRENT_TIMING_COLLECTOR: ContextVar[Optional["RequestTimingCollector"]] = ContextVar(
    "current_timing_collector",
    default=None,
)


class RequestTimingCollector:
    """收集单个请求或后台任务的阶段耗时。

    使用 time.perf_counter() 获取高精度时间戳，记录每个阶段的名称、耗时和状态。
    支持嵌套阶段（通过 contextmanager）和元数据附加。
    """

    def __init__(self, request_path: str, request_kind: str):
        self.trace_id = str(uuid.uuid4())     # 唯一追踪 ID
        self.request_path = request_path       # 请求路径，如 "/api/rag/chat"
        self.request_kind = request_kind       # 请求类型，如 "chat" / "search" / "upload"
        self.started_at = time.perf_counter()  # 请求开始时间戳
        self.completed_at: Optional[float] = None  # 请求完成时间戳
        self.stages: list[dict[str, Any]] = []      # 阶段耗时列表
        self.metadata: dict[str, Any] = {}          # 附加元数据（如 top_k、mode 等）
        self.first_token_ms: Optional[float] = None # 首字输出延迟（流式场景）
        self._logged = False                        # 是否已输出日志

    def set_metadata(self, **values: Any) -> None:
        """附加请求级元数据，None 值会被忽略。"""
        for key, value in values.items():
            if value is None:
                continue
            self.metadata[key] = value

    @contextmanager
    def stage(self, name: str, meta: Optional[dict[str, Any]] = None) -> Iterator[None]:
        """上下文管理器：记录一个阶段的耗时。

        用法：
            with collector.stage("检索"):
                do_retrieval()

        阶段内抛出异常时，status 标记为 "error" 并记录异常类型，异常继续向上抛出。
        """
        started_at = time.perf_counter()
        status = "ok"
        stage_meta = dict(meta or {})
        try:
            yield
        except Exception as exc:
            status = "error"
            stage_meta.setdefault("error_type", type(exc).__name__)
            raise
        finally:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
            self.stages.append(
                {
                    "name": name,
                    "elapsed_ms": elapsed_ms,
                    "status": status,
                    "meta": stage_meta,
                }
            )

    def mark_first_token(self) -> None:
        """标记首字输出时间点（仅首次调用生效）。

        用于流式响应场景，衡量从请求开始到第一个 token 输出的延迟。
        """
        if self.first_token_ms is None:
            self.first_token_ms = round((time.perf_counter() - self.started_at) * 1000, 3)

    def snapshot(self) -> dict[str, Any]:
        """生成当前时刻的耗时快照（不标记完成）。

        可在请求处理过程中多次调用，用于实时获取中间状态。
        """
        end_time = self.completed_at or time.perf_counter()
        payload: dict[str, Any] = {
            "trace_id": self.trace_id,
            "request_path": self.request_path,
            "request_kind": self.request_kind,
            "total_ms": round((end_time - self.started_at) * 1000, 3),
            "stages": list(self.stages),
        }
        if self.first_token_ms is not None:
            payload["first_token_ms"] = self.first_token_ms
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    def finish(self, *, log_enabled: bool = True) -> dict[str, Any]:
        """结束计时，生成最终耗时数据。

        Args:
            log_enabled: 是否输出 INFO 级别日志，默认开启。

        Returns:
            包含 trace_id、total_ms、各阶段耗时的完整字典。
        """
        if self.completed_at is None:
            self.completed_at = time.perf_counter()
        payload = self.snapshot()
        if log_enabled and not self._logged:
            logger.info("[Timing] %s", payload)
            self._logged = True
        return payload


def get_current_timing_collector() -> Optional[RequestTimingCollector]:
    """获取当前协程/线程的计时收集器，未绑定时返回 None。"""
    return _CURRENT_TIMING_COLLECTOR.get()


@contextmanager
def bind_timing_collector(collector: RequestTimingCollector) -> Iterator[RequestTimingCollector]:
    """上下文管理器：将计时收集器绑定到当前 ContextVar。

    在请求开始时调用，请求结束时自动恢复之前的值。
    """
    token: Token = _CURRENT_TIMING_COLLECTOR.set(collector)
    try:
        yield collector
    finally:
        _CURRENT_TIMING_COLLECTOR.reset(token)


@contextmanager
def timing_stage(name: str, meta: Optional[dict[str, Any]] = None) -> Iterator[None]:
    """便捷函数：在当前计时收集器中记录一个阶段。

    若当前未绑定收集器，则直接 yield（无计时操作），调用方无需感知是否存在收集器。
    """
    collector = get_current_timing_collector()
    if collector is None:
        yield
        return
    with collector.stage(name, meta=meta):
        yield
