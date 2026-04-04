"""
数据模型定义模块

该模块定义了数据库表结构对应的 ORM 模型，主要包含：
- ImageRecord：图像记录模型，存储图像元数据和语义描述

所有模型都继承自 Base 基类，与数据库表结构一一对应。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text

from .database import Base


class ImageRecord(Base):
    """图像记录模型
    
    存储图像的元数据和生成的语义描述，对应数据库中的 image_records 表。
    用于跟踪图像的上传、处理状态和生成的描述信息。
    """
    __tablename__ = "image_records"  # 数据库表名

    # 主键字段，使用 UUID 生成唯一标识符
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    
    # 图像文件路径
    file_path = Column(String, nullable=False)
    
    # 上传时间，默认使用当前 UTC 时间
    upload_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # 生成的图像语义描述，可为空（处理中或失败时）
    generated_description = Column(Text, nullable=True)
    
    # 处理状态，默认为 "Processing"，可取值：Processing、Completed、Failed
    status = Column(String, default="Processing", index=True)
    
    # 图像来源数据集，可为空（自定义上传的图像）
    source_dataset = Column(String, nullable=True)
    
    # 图像标签，可为空
    tags = Column(String, nullable=True)
    
    # 额外元数据，使用文本格式存储，可为空
    extra_metadata = Column(Text, nullable=True)
