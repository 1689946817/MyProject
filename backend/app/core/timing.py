"""轻量级请求耗时采集工具。"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Iterator, Optional


logger = logging.getLogger(__name__)

_CURRENT_TIMING_COLLECTOR: ContextVar[Optional["RequestTimingCollector"]] = ContextVar(
    "current_timing_collector",
    default=None,
)


class RequestTimingCollector:
    """收集单个请求或后台任务的阶段耗时。"""

    def __init__(self, request_path: str, request_kind: str):
        self.trace_id = str(uuid.uuid4())
        self.request_path = request_path
        self.request_kind = request_kind
        self.started_at = time.perf_counter()
        self.completed_at: Optional[float] = None
        self.stages: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {}
        self.first_token_ms: Optional[float] = None
        self._logged = False

    def set_metadata(self, **values: Any) -> None:
        for key, value in values.items():
            if value is None:
                continue
            self.metadata[key] = value

    @contextmanager
    def stage(self, name: str, meta: Optional[dict[str, Any]] = None) -> Iterator[None]:
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
        if self.first_token_ms is None:
            self.first_token_ms = round((time.perf_counter() - self.started_at) * 1000, 3)

    def snapshot(self) -> dict[str, Any]:
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
        if self.completed_at is None:
            self.completed_at = time.perf_counter()
        payload = self.snapshot()
        if log_enabled and not self._logged:
            logger.info("[Timing] %s", payload)
            self._logged = True
        return payload


def get_current_timing_collector() -> Optional[RequestTimingCollector]:
    return _CURRENT_TIMING_COLLECTOR.get()


@contextmanager
def bind_timing_collector(collector: RequestTimingCollector) -> Iterator[RequestTimingCollector]:
    token: Token = _CURRENT_TIMING_COLLECTOR.set(collector)
    try:
        yield collector
    finally:
        _CURRENT_TIMING_COLLECTOR.reset(token)


@contextmanager
def timing_stage(name: str, meta: Optional[dict[str, Any]] = None) -> Iterator[None]:
    collector = get_current_timing_collector()
    if collector is None:
        yield
        return
    with collector.stage(name, meta=meta):
        yield
