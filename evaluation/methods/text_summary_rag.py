"""
Text-Summary-RAG 基线方法。

用 proposed 方法（MLLM 描述 + 文本向量检索）检索图片，
但生成阶段只将图片的文字摘要（description 字段）作为上下文传给 LLM，
不传原始图片。

用途：与 proposed_multimodal_rag（传原始图片）进行对比，
验证"传原始图片"比"只传文字摘要"对生成质量的影响差异。
若本方法效果明显差于传图片的方法，则说明 MLLM 能从原始图片中
获取文字摘要未覆盖的视觉细节信息。

返回格式：
    {
        "generated_answer": str,   # LLM 生成的回答
        "context": str,            # 拼接的图片描述文字
        "images": [],              # 不传图片，列表为空
    }
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.langchain_integration.vectorstores import get_coco_proposed_vector_store  # noqa: E402
from app.langchain_integration.models import get_chat_model  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402

# 提示词模板：要求 LLM 仅基于检索到的图片描述文字回答，不允许编造
_PROMPT = (
    "你是一个多模态知识库问答助手。以下是从知识库中检索到的相关图像描述文字，"
    "请基于这些文字信息回答用户的问题。\n\n"
    "检索到的描述：\n{context}\n\n"
    "用户问题：{query}\n\n"
    "请基于以上描述内容进行回答，如果信息不足以回答某些部分，请明确说明不确定。"
)


def retrieve(query: str, top_k: int = 5) -> List[str]:
    """复用 proposed 方法的向量检索，返回图像 ID 列表。

    检索路径与 proposed_multimodal_rag 完全一致，
    区别仅在于生成阶段的上下文传递方式。

    Args:
        query: 查询文本。
        top_k: 返回的检索结果数量，默认 5。

    Returns:
        List[str]: top_k 个预测图像 ID 列表。
    """
    hits = get_coco_proposed_vector_store().search_by_text(query_text=query, top_k=top_k)
    return [str(item["id"]) for item in hits]


async def generate(query: str, top_k: int = 5, extra_context: Optional[str] = None) -> Dict[str, Any]:
    """
    检索图片描述，将描述文字（而非图片本身）作为上下文传给 LLM。

    Args:
        query: 用户问题
        top_k: 检索数量
        extra_context: 来自文本知识库的额外上下文（多模态文档场景）

    Returns:
        dict: {
            "generated_answer": str,
            "context": str,   # 拼接的图片描述文字
            "images": [],     # 不传图片
        }
    """
    results = get_coco_proposed_vector_store().similarity_search_with_score(query, k=top_k)

    descriptions = []
    for doc, _ in results:
        desc = doc.page_content
        if desc:
            descriptions.append(desc)

    context_parts = descriptions
    if extra_context:
        context_parts = [extra_context] + context_parts
    context = "\n\n".join(context_parts)

    model = get_chat_model()
    messages = [HumanMessage(content=_PROMPT.format(context=context, query=query))]
    result = await model._agenerate(messages)

    return {
        "generated_answer": result.generations[0].message.content,
        "context": context,
        "images": [],
    }
