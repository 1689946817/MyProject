"""管理端点路由"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.application.schemas import (
    AdminConfigResponse,
    AdminConfigUpdateRequest,
    AdminConfigUpdateResponse,
)
from app.core.config_admin import ConfigValidationError, ConfigAdminService, get_config_admin_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/rebuild-bm25")
async def rebuild_bm25():
    """手动重建全量 BM25 索引"""
    try:
        from app.retrieval.hybrid import rebuild_bm25_index

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
    from app.retrieval.hybrid import get_bm25_index

    bm25_index = get_bm25_index()
    return {
        "is_ready": bm25_index.is_ready,
        "doc_count": len(bm25_index._doc_ids),
        "index_path": bm25_index.index_path,
    }


@router.get("/config", response_model=AdminConfigResponse)
async def get_config(service: ConfigAdminService = Depends(get_config_admin_service)):
    """获取系统配置页面数据。"""
    return service.get_config_payload()


@router.put("/config", response_model=AdminConfigUpdateResponse)
async def update_config(
    payload: AdminConfigUpdateRequest,
    service: ConfigAdminService = Depends(get_config_admin_service),
):
    """更新 .env 中的配置项。"""
    try:
        return service.update_config_values(payload.values)
    except ConfigValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "field_errors": exc.field_errors,
                "message": exc.message,
            },
        ) from exc
