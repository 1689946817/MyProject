"""
双路检索调度模块

该模块实现了两种检索方式的调度：
1. 文本→图像检索：直接对文本查询进行向量检索
2. 图像→图像检索：先对输入图像生成描述，再基于描述进行文本检索

是连接用户查询和检索系统的核心调度器。
"""
import base64
from typing import Any, Dict, List, Tuple

from fastapi import UploadFile

from app.retrieval.rerank import simple_rerank
from app.retrieval.vector_store import search_by_text
from app.semantic.mllm_client import get_mllm_client
from app.semantic.prompts import IMAGE_DESCRIPTION_PROMPT


async def text_to_image_search(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """文本到图像检索
    
    直接对文本查询进行向量检索，然后对结果进行重排序。
    
    Args:
        query: 文本查询
        top_k: 返回的结果数量，默认为 10
    
    Returns:
        List[Dict[str, Any]]: 重排序后的检索结果列表
    """
    # 基于文本查询向量库
    hits = search_by_text(query_text=query, top_k=top_k)
    # 对结果进行重排序
    return simple_rerank(hits)


async def image_to_image_search(
    file: UploadFile,
    top_k: int = 10,
) -> Tuple[List[Dict[str, Any]], str]:
    """图像到图像检索
    
    先用多模态模型生成输入图像的结构化描述，再基于描述进行文本检索。
    不在此处持久化新的 ImageRecord，仅用于查询。
    
    Args:
        file: 上传的图像文件
        top_k: 返回的结果数量，默认为 10
    
    Returns:
        Tuple[List[Dict[str, Any]], str]: (检索结果列表, 生成的查询描述)
    """
    # 读取文件内容
    contents = await file.read()
    # 将图像转为 base64 编码
    b64_image = base64.b64encode(contents).decode("utf-8")
    # 获取多模态模型客户端
    client = get_mllm_client()
    # 生成图像描述
    description = await client.generate_description(
        image_b64=b64_image,
        prompt=IMAGE_DESCRIPTION_PROMPT,
    )
    # 基于生成的描述进行文本检索
    hits = search_by_text(query_text=description, top_k=top_k)
    # 对结果进行重排序并返回结果和描述
    return simple_rerank(hits), description

