"""
文档记录数据模型

定义 document_records 表的 ORM 模型，用于跟踪 PDF 文档的上传和处理状态。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .database import Base


class DocumentRecord(Base):
    """文档记录模型

    存储 PDF 文档的元数据和处理状态，对应数据库中的 document_records 表。
    """
    __tablename__ = "document_records"

    # 主键，UUID
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))

    # 原始文件名
    file_name = Column(String, nullable=False)

    # 管理端展示标题，可为空
    title = Column(String, nullable=True)

    # 存储路径
    file_path = Column(String, nullable=False)

    # 上传时间
    upload_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 处理状态：Processing / Completed / Failed
    status = Column(String, default="Processing", index=True)

    # 提取的文本片段数量
    chunk_count = Column(Integer, default=0)

    # 提取并处理的图片数量（含表格页渲染图）
    image_count = Column(Integer, default=0)

    # 文档类型，默认 pdf，后续可扩展 markdown 等
    document_type = Column(String, default="pdf", nullable=False, index=True)

    # 文档标签，逗号分隔存储
    tags = Column(String, nullable=True)

    # 管理备注
    notes = Column(Text, nullable=True)

    # 是否启用
    enabled = Column(Boolean, default=True, nullable=False, index=True)

    # 自定义元数据（JSON 字符串）
    custom_metadata = Column(Text, nullable=True)

    # 额外元数据（JSON 字符串）
    extra_metadata = Column(Text, nullable=True)
