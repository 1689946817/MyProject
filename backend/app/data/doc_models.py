"""
文档记录数据模型模块。

定义 document_records 表的 ORM 模型，用于跟踪 PDF 等文档的上传、解析和向量化全过程。
支持多版本管理（logical_asset_id + version_number）、内容去重（content_hash）
和解析进度追踪（parse_stage + progress_percent）。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .database import Base


class DocumentRecord(Base):
    """文档记录模型。

    存储文档的元数据和处理状态，对应数据库中的 document_records 表。
    一条记录代表一个文档的特定版本，涵盖上传到向量化的完整生命周期。
    """

    __tablename__ = "document_records"

    # 主键，UUID 字符串，创建时自动生成
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))

    # 原始上传文件名（含扩展名）
    file_name = Column(String, nullable=False)

    # 管理端展示标题，可为空（默认使用 file_name）
    title = Column(String, nullable=True)

    # 文件在服务器上的存储路径
    file_path = Column(String, nullable=False)

    # 上传时间，UTC 时区
    upload_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 处理状态：Processing（处理中）/ Completed（完成）/ Failed（失败）
    status = Column(String, default="Processing", index=True)

    # 文本解析后得到的片段（chunk）数量
    chunk_count = Column(Integer, default=0)

    # 提取并处理的图片数量（含表格页渲染图）
    image_count = Column(Integer, default=0)

    # 文档类型，默认 "pdf"，后续可扩展 "markdown"、"word" 等
    document_type = Column(String, default="pdf", nullable=False, index=True)

    # 文档标签，逗号分隔存储，用于管理端筛选
    tags = Column(String, nullable=True)

    # 管理端备注信息
    notes = Column(Text, nullable=True)

    # 是否启用（禁用后不参与检索）
    enabled = Column(Boolean, default=True, nullable=False, index=True)

    # 用户自定义元数据（JSON 字符串）
    custom_metadata = Column(Text, nullable=True)

    # 系统额外元数据（JSON 字符串），如解析器版本、页数等
    extra_metadata = Column(Text, nullable=True)

    # 解析后端：local（本地解析）/ mineru（MinerU 远程服务）
    parse_backend = Column(String, default="local", nullable=False, index=True)

    # 解析阶段：queued → submitting → parsing → vectorizing → completed / failed
    parse_stage = Column(String, default="queued", nullable=False, index=True)

    # 解析进度百分比（0-100），前端据此展示进度条
    progress_percent = Column(Integer, default=0, nullable=False)

    # 当前阶段的提示文案，供前端展示（如"正在向量化..."）
    progress_message = Column(Text, nullable=True)

    # 文档内容的哈希值（MD5/SHA256），用于检测重复上传
    content_hash = Column(String, nullable=True, index=True)

    # 逻辑资源 ID，相同 logical_asset_id 的记录视为同一文档的不同版本
    logical_asset_id = Column(String, nullable=True, index=True)

    # 版本号，从 1 开始递增
    version_number = Column(Integer, default=1, nullable=False)

    # 是否为该 logical_asset_id 下的最新版本
    # 用于查询时快速定位当前有效版本
    is_latest = Column(Boolean, default=True, nullable=False, index=True)
