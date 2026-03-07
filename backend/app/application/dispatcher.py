import base64
from typing import Any, Dict, List, Tuple

from fastapi import UploadFile

from app.retrieval.rerank import simple_rerank
from app.retrieval.vector_store import search_by_text
from app.semantic.mllm_client import get_mllm_client
from app.semantic.prompts import IMAGE_DESCRIPTION_PROMPT


async def text_to_image_search(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    文本→图像检索：直接对文本进行向量检索并重排序。
    """
    hits = search_by_text(query_text=query, top_k=top_k)
    return simple_rerank(hits)


async def image_to_image_search(
    file: UploadFile,
    top_k: int = 10,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    图像→图像检索：先用多模态模型生成结构化描述，再基于描述进行文本检索。
    不在此处持久化新的 ImageRecord，仅用于查询。
    返回 (检索结果列表, 生成的查询描述)。
    """
    contents = await file.read()
    b64_image = base64.b64encode(contents).decode("utf-8")
    client = get_mllm_client()
    description = await client.generate_description(
        image_b64=b64_image,
        prompt=IMAGE_DESCRIPTION_PROMPT,
    )
    hits = search_by_text(query_text=description, top_k=top_k)
    return simple_rerank(hits), description

