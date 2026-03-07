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
    """
    同步处理一批上传图片：保存文件、生成记录、调用多模态模型生成描述并更新记录，
    同时将描述写入向量库。
    返回 (ImageRecord, description) 列表。
    """
    client = get_mllm_client()
    results: List[Tuple[ImageRecord, str]] = []

    for file in files:
        contents = await file.read()

        record = ImageRecord(
            file_path="",
            status="Processing",
            source_dataset=source_dataset,
        )
        db.add(record)
        db.flush()  # 确保生成 id

        image_path = get_image_path(record.id, split=split)
        image_path.write_bytes(contents)
        record.file_path = str(image_path)
        db.add(record)
        db.commit()
        db.refresh(record)

        # 将图片转为 base64，交给多模态接口
        b64_image = base64.b64encode(contents).decode("utf-8")
        prompt = IMAGE_DESCRIPTION_PROMPT

        # 调用多模态模型生成描述
        description = await client.generate_description(
            image_b64=b64_image,
            prompt=prompt,
        )

        record.generated_description = description
        record.status = "Completed"
        db.add(record)
        db.commit()
        db.refresh(record)

        # 写入向量库
        upsert_image_description(
            doc_id=record.id,
            text=description,
            metadata={
                "file_path": record.file_path,
                "source_dataset": record.source_dataset,
            },
        )

        results.append((record, description))

    return results

