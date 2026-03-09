"""
数据库连接管理模块

该模块负责配置 SQLAlchemy 数据库连接和会话管理，包括：
- 创建数据库引擎
- 配置会话工厂
- 定义基类模型
- 提供数据库会话依赖注入函数

支持 SQLite 数据库（开发环境）和其他 SQL 数据库。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings


# 创建数据库引擎
# 对于 SQLite 数据库，需要设置 check_same_thread=False 以支持多线程访问
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    connect_args={"check_same_thread": False} if settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite") else {},
)

# 创建会话工厂，配置为非自动提交和非自动刷新
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明基类，所有 ORM 模型都继承自这个基类
Base = declarative_base()


def get_db():
    """获取数据库会话
    
    提供一个依赖注入函数，用于在 FastAPI 路由中获取数据库会话。
    使用生成器模式确保会话在使用后正确关闭，避免资源泄漏。
    
    Yields:
        Session: 数据库会话实例
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        # 无论操作是否成功，都会关闭会话
        db.close()

