"""
管理端点路由。

本模块提供面向运维管理员的管理接口，目前包含两大功能域：

1. **BM25 索引管理**：
   - 手动触发全量重建（`POST /rebuild-bm25`）。
   - 查询索引当前状态（`GET /bm25-status`）。
   典型使用场景：后台定时重建失败后的人工补救，或新数据批量导入后刷新索引。

2. **系统配置管理**：
   - 获取当前运行配置（`GET /config`），用于前端配置页面渲染。
   - 更新配置项（`PUT /config`），写入 `.env` 文件。
   - 调度后端重启（`POST /restart`），使已保存配置重新加载。

注意：这些端点目前未做鉴权保护，仅应在受信内网或反向代理鉴权层之后暴露。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.schemas import (
    AdminConfigResponse,
    AdminConfigUpdateRequest,
    AdminConfigUpdateResponse,
    AdminRestartResponse,
)
from app.core.config_admin import ConfigValidationError, ConfigAdminService, get_config_admin_service
from app.core.restart import schedule_backend_restart

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路由注册
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# BM25 索引管理
# ---------------------------------------------------------------------------

@router.post("/rebuild-bm25")
async def rebuild_bm25():
    """手动触发全量 BM25 索引重建。

    流程：遍历所有已入库文档，重新分词并写入 BM25 索引文件。
    重建期间旧索引仍可服务，完成后自动替换。

    Returns:
        成功时返回 {"status": "ok", "doc_count": int, "index_path": str}。
        失败时返回 {"status": "error", "detail": str}，同时记录错误日志。
    """
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
    """查看 BM25 索引的当前状态。

    返回索引是否就绪（is_ready）、已索引文档数量以及持久化文件路径。
    前端可据此判断是否需要触发重建操作。

    Returns:
        {"is_ready": bool, "doc_count": int, "index_path": str}
    """
    from app.retrieval.hybrid import get_bm25_index

    bm25_index = get_bm25_index()
    return {
        "is_ready": bm25_index.is_ready,
        "doc_count": len(bm25_index._doc_ids),
        "index_path": bm25_index.index_path,
    }


# ---------------------------------------------------------------------------
# 系统配置管理
# ---------------------------------------------------------------------------

@router.get("/config", response_model=AdminConfigResponse)
async def get_config(service: ConfigAdminService = Depends(get_config_admin_service)):
    """获取系统配置页面数据。

    由 ConfigAdminService 从 .env 文件读取当前配置值，
    并附带字段元数据（类型、描述、取值范围等），供前端渲染配置表单。

    Args:
        service: 配置管理服务实例（通过依赖注入）。

    Returns:
        AdminConfigResponse，包含配置项列表与当前值。
    """
    return service.get_config_payload()


@router.put("/config", response_model=AdminConfigUpdateResponse)
async def update_config(
    payload: AdminConfigUpdateRequest,
    service: ConfigAdminService = Depends(get_config_admin_service),
):
    """更新 .env 中的配置项。

    接受前端提交的 key-value 对，由 ConfigAdminService 校验合法性后
    写入 `.env` 文件。部分配置项可即时生效，部分需要重启后端服务。

    校验失败时返回 422 状态码，并在 detail 中附带逐字段的错误信息
    （field_errors）与人类可读的 message。

    Args:
        payload: 包含待更新键值对的请求体。
        service: 配置管理服务实例（通过依赖注入）。

    Returns:
        AdminConfigUpdateResponse，包含更新结果与生效说明。

    Raises:
        HTTPException(422): 当配置值未通过校验时。
    """
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


@router.post(
    "/restart",
    response_model=AdminRestartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def restart_backend():
    """调度后端服务重启。

    接口先返回 202 响应，再由后台线程延迟重启当前 Python 进程，
    避免请求尚未完成时连接被立即中断。
    """
    schedule_backend_restart()
    return {
        "success": True,
        "message": "后端正在重启，请稍后刷新页面。",
        "restart_scheduled": True,
    }
