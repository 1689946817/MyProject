"""
图像描述生成服务模块

该模块负责处理图像上传和描述生成流程，包括：
- 保存上传的图像文件
- 生成图像记录到数据库
- 调用多模态模型生成结构化描述
- 更新数据库记录
- 将描述写入向量库

是连接用户上传、模型处理和向量存储的核心服务。
"""
import base64
from typing import Iterable, List, Tuple

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.data.models import ImageRecord
from app.data.storage import ImageSplit, get_image_path
from app.retrieval.vector_store import upsert_image_description
from app.semantic.mllm_client import get_mllm_client
from app.semantic.prompts import IMAGE_DESCRIPTION_PROMPT


async def process_image_uploads(
    db: Session,
    files: Iterable[UploadFile],
    split: ImageSplit = "custom",
    source_dataset: str | None = None,
) -> List[Tuple[ImageRecord, str]]:
    """处理批量图像上传
    
    处理一批上传的图像文件，包括以下步骤：
    1. 读取文件内容
    2. 创建数据库记录
    3. 保存图像文件到存储目录
    4. 调用多模态模型生成结构化描述
    5. 更新数据库记录状态和描述
    6. 将描述写入向量库
    
    Args:
        db: 数据库会话
        files: 上传的文件对象集合
        split: 数据集分割类型，默认为 "custom"
        source_dataset: 图像来源数据集，可为空
    
    Returns:
        List[Tuple[ImageRecord, str]]: 包含图像记录和生成描述的列表
    
    Raises:
        Exception: 处理过程中发生错误时抛出
    """
    # 获取多模态模型客户端
    client = get_mllm_client()
    results: List[Tuple[ImageRecord, str]] = []

    # 遍历处理每个上传的文件
    for file in files:
        # 读取文件内容
        contents = await file.read()

        # 创建图像记录，初始状态为 Processing
        record = ImageRecord(
            file_path="",  # 稍后更新
            status="Processing",
            source_dataset=source_dataset,
        )
        # 添加到数据库并刷新以获取生成的 ID
        db.add(record)
        db.flush()  # 确保生成 id

        # 获取图像存储路径并保存文件
        image_path = get_image_path(record.id, split=split)
        image_path.write_bytes(contents)
        # 更新记录的文件路径
        record.file_path = str(image_path)
        db.add(record)
        db.commit()
        db.refresh(record)

        # 将图片转为 base64 编码，用于多模态模型接口
        b64_image = base64.b64encode(contents).decode("utf-8")
        prompt = IMAGE_DESCRIPTION_PROMPT

        # 调用多模态模型生成描述
        description = await client.generate_description(
            image_b64=b64_image,
            prompt=prompt,
        )

        # 更新记录的描述和状态
        record.generated_description = description
        record.status = "Completed"
        db.add(record)
        db.commit()
        db.refresh(record)

        # 将描述写入向量库，用于后续检索
        upsert_image_description(
            doc_id=record.id,
            text=description,
            metadata={
                "file_path": record.file_path,
                "source_dataset": record.source_dataset,
            },
        )

        # 添加到结果列表
        results.append((record, description))

    return results

