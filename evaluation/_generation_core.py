"""
生成评估公共逻辑：图片读取、MLLM 调用、结果写入。
由 run_gen_image_only.py 和 run_gen_multimodal.py 共同引用。
"""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from app.langchain_integration.models import get_chat_model  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402

from evaluation.datasets.coco_subset import CocoQuerySample, load_coco_subset  # noqa: E402

_RAG_WITH_IMAGE_PROMPT = (
    "你是一个多模态知识库问答助手。你将看到若干张检索到的相关图像，"
    "以及用户提出的问题。请仔细观察这些图像的内容，基于图像中的视觉信息回答用户的问题。\n\n"
    "用户问题：{query}\n\n"
    "{extra_context_section}"
    "请基于图像内容进行回答，可以自然地引用相关图像，例如'根据第一张图像，可以看到……'。"
    "如果图像信息不足以回答某些部分，请明确说明不确定。"
)
_EXTRA_CONTEXT_SECTION = "参考文档内容：\n{extra_context}\n\n"


def _build_image_data_url(image_b64: str, file_path: str = "") -> str:
    mime_type, _ = mimetypes.guess_type(file_path) if file_path else (None, None)
    actual_mime_type = mime_type if mime_type and mime_type.startswith("image/") else "image/jpeg"
    return f"data:{actual_mime_type};base64,{image_b64}"


def ids_to_file_paths(ids: List[str]) -> List[str]:
    """将图像 ID 列表转换为文件路径列表（从 ChromaDB 元数据中查询）。"""
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from app.core.config import settings as app_settings

    client = chromadb.Client(
        ChromaSettings(is_persistent=True, persist_directory=app_settings.CHROMA_PERSIST_DIR)
    )
    id_to_path: Dict[str, str] = {}
    for col_name in [
        app_settings.COCO_PROPOSED_COLLECTION_NAME,
        "images_multimodal_embedding",
        "images_ocr_text",
    ]:
        try:
            col = client.get_collection(col_name)
            result = col.get(ids=ids, include=["metadatas"])
            for img_id, meta in zip(result["ids"], result["metadatas"]):
                if img_id not in id_to_path and meta and meta.get("file_path"):
                    id_to_path[img_id] = meta["file_path"]
        except Exception:
            continue
        if len(id_to_path) == len(ids):
            break
    return [id_to_path.get(i, "") for i in ids]


def read_image_as_base64(file_path: str) -> Optional[tuple[str, str]]:
    if not file_path or not os.path.exists(file_path):
        return None
    with open(file_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    return image_b64, file_path


async def generate_with_images(
    query: str,
    image_payloads: List[tuple[str, str]],
    extra_context: Optional[str] = None,
) -> str:
    """将检索到的图像（+ 可选文档上下文）送入 MLLM 生成答案。"""
    if not image_payloads:
        return "未找到相关图像，无法回答问题。"

    extra_section = (
        _EXTRA_CONTEXT_SECTION.format(extra_context=extra_context) if extra_context else ""
    )
    prompt_text = _RAG_WITH_IMAGE_PROMPT.format(query=query, extra_context_section=extra_section)

    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt_text}]
    for idx, (image_b64, file_path) in enumerate(image_payloads, start=1):
        content.append({"type": "image_url", "image_url": {"url": _build_image_data_url(image_b64, file_path)}})
        content.append({"type": "text", "text": f"\n[图像 {idx}]"})

    model = get_chat_model()
    result = await model._agenerate([HumanMessage(content=content)])
    return result.generations[0].message.content


async def run_generation(
    samples: List[CocoQuerySample],
    method: str,
    top_k: int,
    output_path: Path,
    run_one_sample,  # callable: async (sample, method, top_k) -> dict
) -> None:
    records = []
    total = len(samples)
    for i, sample in enumerate(samples, start=1):
        print(f"[{i}/{total}] method={method}  query={sample.query[:60]}")
        record = await run_one_sample(sample, method, top_k)
        records.append(record)
        output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done. {len(records)} records saved to {output_path}")
