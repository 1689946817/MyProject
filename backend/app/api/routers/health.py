"""
健康检查与指标路由。

本模块提供系统运行状态的探测端点，供负载均衡器、容器编排（Kubernetes liveness/readiness probe）
以及 Prometheus 监控系统使用。端点分为三层：

- **Liveness**：仅确认进程存活，不依赖外部组件。
- **Dependencies**：深入检查数据库（SQLite）、向量数据库（ChromaDB）、BM25 索引及后台 Worker 心跳。
- **Readiness**：基于依赖检查结果判断服务是否可以接收流量（允许 degraded 状态）。
- **Metrics**：以 Prometheus 文本格式暴露内部计数器与 Job 队列统计。

所有检查函数遵循同一模式：捕获异常并返回结构化字典而非抛出异常，确保单一组件故障不会
阻断整份健康报告的返回。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.application.operations import get_recent_worker_heartbeats
from app.application.schemas import HealthStatusResponse
from app.core.metrics import get_metrics_registry
from app.data.database import get_db

# ---------------------------------------------------------------------------
# 路由注册
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["health"])


# ---------------------------------------------------------------------------
# 内部辅助函数 — 各组件探针
# ---------------------------------------------------------------------------

def _check_database(db: Session) -> dict:
    """检查数据库连接是否可用。

    执行轻量级 `SELECT 1` 探测 SQLAlchemy 会话能否正常工作。
    若连接池耗尽或文件锁冲突将返回 {"status": "error", "detail": "..."}。

    Args:
        db: SQLAlchemy 数据库会话（由 FastAPI 依赖注入提供）。

    Returns:
        包含 "status" 键的字典，可能额外包含 "detail" 错误描述。
    """
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:  # pragma: no cover - defensive
        return {"status": "error", "detail": str(exc)}


def _check_chroma() -> dict:
    """检查 ChromaDB 向量数据库是否可访问，并返回集合统计。

    分别获取图片集合与文档集合的条目数量。任一集合加载失败即视为 error。

    Returns:
        正常时返回 {"status": "ok", "image_count": int, "document_count": int}。
        异常时返回 {"status": "error", "detail": str}。
    """
    try:
        from app.langchain_integration.vectorstores import get_document_vector_store, get_vector_store

        image_count = get_vector_store().vectorstore._collection.count()
        document_count = get_document_vector_store()._vectorstore._collection.count()
        return {"status": "ok", "image_count": image_count, "document_count": document_count}
    except Exception as exc:  # pragma: no cover - defensive
        return {"status": "error", "detail": str(exc)}


def _check_bm25() -> dict:
    """检查 BM25 全文检索索引是否就绪。

    索引未加载时 `is_ready` 为 False，此时状态标记为 "degraded"（非 error），
    因为系统仍可依赖纯向量检索降级运行。

    Returns:
        包含 "status" 和 "doc_count" 的字典。
    """
    try:
        from app.retrieval.hybrid import get_bm25_index

        index = get_bm25_index()
        return {"status": "ok" if index.is_ready else "degraded", "doc_count": len(index._doc_ids)}
    except Exception as exc:  # pragma: no cover - defensive
        return {"status": "error", "detail": str(exc)}


# ---------------------------------------------------------------------------
# 端点 — Liveness / Dependencies / Readiness / Metrics
# ---------------------------------------------------------------------------

@router.get("/health/live", response_model=HealthStatusResponse)
def live() -> HealthStatusResponse:
    """Liveness 探针：仅确认进程存活。

    适合用作 Kubernetes livenessProbe，不检查任何外部依赖，
    只要进程能响应即返回 ok。
    """
    return HealthStatusResponse(status="ok", checks={"process": {"status": "ok"}}, generated_at=datetime.utcnow())


@router.get("/health/deps", response_model=HealthStatusResponse)
def deps(db: Session = Depends(get_db)) -> HealthStatusResponse:
    """依赖检查：全面探测数据库、ChromaDB、BM25 与 Worker 心跳。

    综合所有组件状态得出总体状态：
    - 任一组件 error  → 整体 error
    - 任一组件 degraded（无 error） → 整体 degraded
    - 全部 ok → 整体 ok

    适合运维监控面板使用，也可作为 Readiness 的基础。
    """
    worker_heartbeats = get_recent_worker_heartbeats(db, within_seconds=300)
    checks = {
        "database": _check_database(db),
        "chroma": _check_chroma(),
        "bm25": _check_bm25(),
        "workers": {
            "status": "ok" if worker_heartbeats else "degraded",
            "active_workers": len(worker_heartbeats),
        },
    }
    overall = "ok"
    if any(item.get("status") == "error" for item in checks.values()):
        overall = "error"
    elif any(item.get("status") == "degraded" for item in checks.values()):
        overall = "degraded"
    return HealthStatusResponse(status=overall, checks=checks, generated_at=datetime.utcnow())


@router.get("/health/ready", response_model=HealthStatusResponse)
def ready(db: Session = Depends(get_db)) -> HealthStatusResponse:
    """Readiness 探针：判断服务是否可以接收外部流量。

    逻辑：
    - 复用 `deps()` 获取各组件状态。
    - 仅当总体为 "error" 时才返回 "error"（拒绝流量）。
    - "degraded" 视为可服务（降级接受流量），适合 Kubernetes readinessProbe。

    这样即使 BM25 索引未加载，服务仍可接收请求并以纯向量检索响应。
    """
    payload = deps(db)
    ready_status = "ok" if payload.status in {"ok", "degraded"} else "error"
    return HealthStatusResponse(status=ready_status, checks=payload.checks, generated_at=payload.generated_at)


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(db: Session = Depends(get_db)) -> PlainTextResponse:
    """Prometheus 指标端点：输出应用内部计数器与 Job 队列统计。

    返回格式遵循 Prometheus text exposition 格式，可直接被 Prometheus
    或兼容的监控系统抓取。指标来源包括：
    1. 内部 MetricsRegistry（请求计数、重试次数等）。
    2. job_tasks 表按状态分组的实时数量（codex_job_tasks_total gauge）。
    """
    metrics_text = get_metrics_registry().render_prometheus()
    job_rows = db.execute(text("SELECT status, COUNT(*) FROM job_tasks GROUP BY status")).fetchall()
    metrics_lines = [metrics_text.rstrip("\n"), "# HELP codex_job_tasks_total Current job count by status.", "# TYPE codex_job_tasks_total gauge"]
    for status, count in job_rows:
        metrics_lines.append(f'codex_job_tasks_total{{status="{status}"}} {count}')
    metrics_lines.append("")
    return PlainTextResponse("\n".join(metrics_lines))
