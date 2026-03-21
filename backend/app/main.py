"""
FastAPI 应用主入口

该模块负责创建和配置 FastAPI 应用，包括：
- 初始化数据库表
- 配置 CORS 中间件
- 注册 API 路由
- 添加健康检查接口

是后端服务的入口点。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from .api.routers import chat, kb, search, docs
from .core.config import settings
from .data.database import Base, engine
# 导入所有 ORM 模型，确保 Base.metadata.create_all() 建表时能发现它们
from .data import models  # noqa: F401
from .data import doc_models  # noqa: F401


def create_app() -> FastAPI:
    """创建 FastAPI 应用
    
    初始化数据库表，配置应用参数，添加中间件，注册路由。
    
    Returns:
        FastAPI: 配置好的 FastAPI 应用实例
    """
    # 创建数据库表结构
    Base.metadata.create_all(bind=engine)

    # 创建 FastAPI 应用实例
    app = FastAPI(
        title="Multimodal RAG Knowledge Base",
        version="0.1.0",
        description="基于多模态大模型与双路检索的多模态RAG知识库系统后端服务",
    )

    # 配置 CORS 中间件，允许前端开发服务器访问
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):(5173|5174|5175)",
        allow_credentials=True,
        allow_methods=["*"],  # 允许所有 HTTP 方法
        allow_headers=["*"],  # 允许所有 HTTP 头
    )

    # 注册 API 路由
    app.include_router(kb.router)  # 知识库管理路由
    app.include_router(search.router)  # 搜索路由
    app.include_router(chat.router)  # RAG 聊天路由
    app.include_router(docs.router)  # 文档知识库路由

    # 挂载静态文件目录，供前端预览图片
    storage_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage")
    os.makedirs(storage_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=storage_dir), name="static")

    # 添加健康检查接口
    @app.get("/api/health", tags=["health"])
    async def health_check() -> dict:
        """健康检查接口
        
        返回服务状态，用于监控和部署。
        
        Returns:
            dict: 包含状态信息的字典
        """
        return {"status": "ok"}

    return app


# 创建应用实例
app = create_app()

