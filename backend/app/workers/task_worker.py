"""
轻量级数据库轮询 worker。
"""
from __future__ import annotations

import asyncio
import os
import socket

from app.application.operations import (
    claim_next_job,
    complete_job,
    fail_job,
    load_json_dict,
    record_worker_heartbeat,
)
from app.application.knowledge_management import ensure_knowledge_management_columns
from app.data.database import SessionLocal
from app.langchain_integration.adapters import get_langchain_adapter


POLL_SECONDS = float(os.getenv("JOB_WORKER_POLL_SECONDS", "2"))
WORKER_ID = os.getenv("JOB_WORKER_ID", f"{socket.gethostname()}-worker")


async def process_once() -> bool:
    adapter = get_langchain_adapter()
    with SessionLocal() as db:
        ensure_knowledge_management_columns(db)
        record_worker_heartbeat(db, worker_id=WORKER_ID, details={"poll_seconds": POLL_SECONDS})
        job = claim_next_job(db, worker_id=WORKER_ID)
        if job is None:
            return False
        payload = load_json_dict(job.payload_json)
        doc_id = str(payload.get("doc_id", "")).strip()
        try:
            if job.job_type == "document_parse":
                await adapter.process_document_record_task(doc_id)
            elif job.job_type == "document_reprocess":
                await adapter.reprocess_document_record_task(doc_id)
            else:
                raise ValueError(f"unsupported job type: {job.job_type}")
            complete_job(db, job, result={"doc_id": doc_id})
            return True
        except Exception as exc:  # pragma: no cover - worker runtime path
            fail_job(db, job, error_message=str(exc), retryable=True)
            return True


async def main() -> None:
    while True:
        did_work = await process_once()
        if not did_work:
            await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
