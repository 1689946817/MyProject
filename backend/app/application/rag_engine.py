from typing import Any, Dict, List, Optional, Tuple

from fastapi import UploadFile

from app.application.dispatcher import image_to_image_search, text_to_image_search
from app.application.llm_client import get_llm_client


def _format_retrieved_context(items: List[Dict[str, Any]]) -> str:
    """
    将检索到的图像描述与元数据格式化为文本上下文，供 LLM 使用。
    """
    lines: List[str] = []
    for idx, item in enumerate(items, start=1):
        meta = item.get("metadata") or {}
        file_path = meta.get("file_path", "")
        desc = item.get("document", "")
        lines.append(f"[图像 {idx}] id={item.get('id')} path={file_path}\n描述：{desc}\n")
    return "\n".join(lines)


async def rag_chat(
    query: str,
    top_k: int = 5,
    image: Optional[UploadFile] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    RAG 问答主流程：
    - 若提供图片，则先以图搜图得到相关图像；否则使用文本检索。
    - 将检索到的图像描述与用户问题拼接为上下文，交给 LLM 生成回答。
    返回 (答案文本, 检索结果列表)。
    """
    if image is not None:
        retrieved, _desc = await image_to_image_search(file=image, top_k=top_k)
    else:
        retrieved = await text_to_image_search(query=query, top_k=top_k)

    context = _format_retrieved_context(retrieved)

    system_prompt = (
        "你是一个多模态知识库问答助手。你会得到若干与图片相关的结构化文本描述，"
        "以及用户提出的问题。请严格基于提供的描述进行回答，不要臆造描述中不存在的细节；"
        "如果描述信息不足以回答某些部分，请明确说明不确定。\n"
        "在回答中可以自然地引用相关图像编号，例如“根据图像1和图像2，可以看出……”。"
    )

    user_content = (
        f"以下是检索到的图像描述：\n{context}\n\n"
        f"用户问题：{query}\n"
        "请基于这些图像描述回答用户的问题。"
    )

    client = get_llm_client()
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    answer = await client.chat(messages=messages)
    return answer, retrieved

