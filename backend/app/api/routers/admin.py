"""管理端点路由"""
import logging

from fastapi import APIRouter

from app.retrieval.hybrid import rebuild_bm25_index, get_bm25_index

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/rebuild-bm25")
async def rebuild_bm25():
    """手动重建全量 BM25 索引"""
    try:
        bm25_index = rebuild_bm25_index()
        return {
            "status": "ok",
            "doc_count": len(bm25_index._doc_ids),
            "index_path": bm25_index.index_path,
        }
    except Exception as e:
        logger.error(f"[Admin] BM25 重建失败: {e}")
        return {"status": "error", "detail": str(e)}


@router.get("/bm25-status")
async def bm25_status():
    """查看 BM25 索引状态"""
    bm25_index = get_bm25_index()
    return {
        "is_ready": bm25_index.is_ready,
        "doc_count": len(bm25_index._doc_ids),
        "index_path": bm25_index.index_path,
    }
