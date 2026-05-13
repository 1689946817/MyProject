"""
轻量级数据库轮询 worker。

以固定间隔轮询数据库中的待处理任务（document_parse / document_reprocess），
调用 LangChainAdapter 执行解析，完成后标记任务状态。

启动方式：python -m app.workers.task_worker
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


POLL_SECONDS = float(os.getenv("JOB_WORKER_POLL_SECONDS", "2"))  # 轮询间隔（秒）
WORKER_ID = os.getenv("JOB_WORKER_ID", f"{socket.gethostname()}-worker")  # worker 唯一标识


async def process_once() -> bool:
    """尝试领取并处理一个任务。无待处理任务时返回 False。"""
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
            # 根据任务类型分发处理
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
    """无限循环轮询：处理任务 → 等待 → 再次轮询。"""
    while True:
        did_work = await process_once()
        if not did_work:
            await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
