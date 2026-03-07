from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routers import chat, kb, search
from .core.config import settings
from .data.database import Base, engine


def create_app() -> FastAPI:
    # 创建数据库表
    Base.metadata.create_all(bind=engine)

    app = FastAPI(
        title="Multimodal RAG Knowledge Base",
        version="0.1.0",
        description="基于多模态大模型与双路检索的多模态RAG知识库系统后端服务",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(kb.router)
    app.include_router(search.router)
    app.include_router(chat.router)

    @app.get("/api/health", tags=["health"])
    async def health_check() -> dict:
        return {"status": "ok"}

    return app


app = create_app()

