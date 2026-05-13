"""
轻量级进程内 HTTP 指标采集模块。

提供 Prometheus 兼容格式的 HTTP 请求计数和累计耗时统计。
通过中间件集成，自动记录每个请求的方法、路径、状态码和耗时。
数据仅保存在内存中，重启后清零，适合开发和轻量部署场景。
"""
from __future__ import annotations

from collections import defaultdict
from threading import Lock


class MetricsRegistry:
    """HTTP 请求指标注册表。

    维护两组计数器：
    - 请求计数：按 (method, path, status_code) 分组统计总请求数
    - 累计耗时：按 (method, path) 分组统计总耗时（毫秒）

    线程安全，通过 Lock 保护所有写操作。
    """

    def __init__(self) -> None:
        self._lock = Lock()
        # 请求计数：(HTTP方法, 路径, 状态码) → 累计次数
        self._request_count: dict[tuple[str, str, int], int] = defaultdict(int)
        # 累计耗时：(HTTP方法, 路径) → 累计毫秒数
        self._request_total_ms: dict[tuple[str, str], float] = defaultdict(float)

    def observe_request(self, *, method: str, path: str, status_code: int, duration_ms: float) -> None:
        """记录一次 HTTP 请求的指标。

        通常由 FastAPI 中间件在请求结束时调用。

        Args:
            method: HTTP 方法（GET/POST 等）
            path: 请求路径
            status_code: 响应状态码
            duration_ms: 请求处理耗时（毫秒）
        """
        with self._lock:
            self._request_count[(method, path, status_code)] += 1
            self._request_total_ms[(method, path)] += float(duration_ms)

    def render_prometheus(self) -> str:
        """将指标渲染为 Prometheus 文本格式。

        输出两组指标：
        - codex_http_requests_total: 按 method/path/status 分组的请求计数器
        - codex_http_request_duration_milliseconds_sum: 按 method/path 分组的累计耗时

        可直接被 Prometheus 或兼容系统抓取。
        """
        lines = [
            "# HELP codex_http_requests_total Total HTTP requests observed by method, path and status.",
            "# TYPE codex_http_requests_total counter",
        ]
        with self._lock:
            # 按 key 排序输出，保证每次渲染结果一致
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


# 模块级单例，全局共享同一个指标注册表
_metrics_registry = MetricsRegistry()


def get_metrics_registry() -> MetricsRegistry:
    """获取全局 MetricsRegistry 单例。"""
    return _metrics_registry
