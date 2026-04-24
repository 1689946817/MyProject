"""
轻量级进程内指标采集。
"""
from __future__ import annotations

from collections import defaultdict
from threading import Lock


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._request_count: dict[tuple[str, str, int], int] = defaultdict(int)
        self._request_total_ms: dict[tuple[str, str], float] = defaultdict(float)

    def observe_request(self, *, method: str, path: str, status_code: int, duration_ms: float) -> None:
        with self._lock:
            self._request_count[(method, path, status_code)] += 1
            self._request_total_ms[(method, path)] += float(duration_ms)

    def render_prometheus(self) -> str:
        lines = [
            "# HELP codex_http_requests_total Total HTTP requests observed by method, path and status.",
            "# TYPE codex_http_requests_total counter",
        ]
        with self._lock:
            for (method, path, status_code), count in sorted(self._request_count.items()):
                lines.append(
                    f'codex_http_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}'
                )
            lines.extend(
                [
                    "# HELP codex_http_request_duration_milliseconds_sum Accumulated request duration in milliseconds.",
                    "# TYPE codex_http_request_duration_milliseconds_sum counter",
                ]
            )
            for (method, path), total_ms in sorted(self._request_total_ms.items()):
                lines.append(
                    f'codex_http_request_duration_milliseconds_sum{{method="{method}",path="{path}"}} {round(total_ms, 3)}'
                )
        lines.append("")
        return "\n".join(lines)


_metrics_registry = MetricsRegistry()


def get_metrics_registry() -> MetricsRegistry:
    return _metrics_registry
