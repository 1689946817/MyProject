"""健康检查与指标路由。"""
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


router = APIRouter(prefix="/api", tags=["health"])


def _check_database(db: Session) -> dict:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:  # pragma: no cover - defensive
        return {"status": "error", "detail": str(exc)}


def _check_chroma() -> dict:
    try:
        from app.langchain_integration.vectorstores import get_document_vector_store, get_vector_store

        image_count = get_vector_store().vectorstore._collection.count()
        document_count = get_document_vector_store()._vectorstore._collection.count()
        return {"status": "ok", "image_count": image_count, "document_count": document_count}
    except Exception as exc:  # pragma: no cover - defensive
        return {"status": "error", "detail": str(exc)}


def _check_bm25() -> dict:
    try:
        from app.retrieval.hybrid import get_bm25_index

        index = get_bm25_index()
        return {"status": "ok" if index.is_ready else "degraded", "doc_count": len(index._doc_ids)}
    except Exception as exc:  # pragma: no cover - defensive
        return {"status": "error", "detail": str(exc)}


@router.get("/health/live", response_model=HealthStatusResponse)
def live() -> HealthStatusResponse:
    return HealthStatusResponse(status="ok", checks={"process": {"status": "ok"}}, generated_at=datetime.utcnow())


@router.get("/health/deps", response_model=HealthStatusResponse)
def deps(db: Session = Depends(get_db)) -> HealthStatusResponse:
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
    payload = deps(db)
    ready_status = "ok" if payload.status in {"ok", "degraded"} else "error"
    return HealthStatusResponse(status=ready_status, checks=payload.checks, generated_at=payload.generated_at)


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(db: Session = Depends(get_db)) -> PlainTextResponse:
    metrics_text = get_metrics_registry().render_prometheus()
    job_rows = db.execute(text("SELECT status, COUNT(*) FROM job_tasks GROUP BY status")).fetchall()
    metrics_lines = [metrics_text.rstrip("\n"), "# HELP codex_job_tasks_total Current job count by status.", "# TYPE codex_job_tasks_total gauge"]
    for status, count in job_rows:
        metrics_lines.append(f'codex_job_tasks_total{{status="{status}"}} {count}')
    metrics_lines.append("")
    return PlainTextResponse("\n".join(metrics_lines))
