"""
数据库连接管理模块。

该模块负责配置 SQLAlchemy 数据库连接和会话管理，包括：
- 创建数据库引擎（engine）
- 配置会话工厂（SessionLocal）
- 定义 ORM 基类（Base）
- 提供数据库会话依赖注入函数（get_db）

默认使用 SQLite 数据库（开发环境），连接串从 settings.SQLALCHEMY_DATABASE_URI 读取。
SQLite 需要特殊配置 check_same_thread=False 以支持 FastAPI 的多线程访问。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings


# 创建数据库引擎
# connect_args 仅对 SQLite 生效：禁用同线程检查，允许跨线程共享连接
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    connect_args={"check_same_thread": False} if settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite") else {},
)

# 创建会话工厂
# autocommit=False: 需要显式调用 commit() 提交事务
# autoflush=False: 查询前不会自动将未提交的更改刷入数据库
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明基类，所有 ORM 模型（ChatSession、DocumentRecord 等）都继承自这个基类
# Base.metadata.create_all(engine) 可用于建表
Base = declarative_base()


def get_db():
    """获取数据库会话的依赖注入生成器。

    在 FastAPI 路由中通过 Depends(get_db) 注入，自动管理会话生命周期。
    使用 try/finally 确保无论操作成功或失败，会话都会被正确关闭。

    Yields:
        Session: SQLAlchemy 数据库会话实例
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        # 无论操作是否成功，都会关闭会话，释放数据库连接
        db.close()

