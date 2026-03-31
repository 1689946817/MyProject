"""
上下文压缩模块

在检索重排序后、LLM 生成前，用文本 LLM 过滤每个文档中与 query 无关的内容，
减少噪声、降低 token 消耗、提升回答质量。
"""
import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

COMPRESSION_PROMPT = """你是一个信息提取专家。给定用户查询和一段文档内容，请仅提取与查询直接相关的信息。

用户查询：{query}

文档内容：
{document}

要求：
- 只保留与查询相关的关键信息
- 如果文档完全无关，回复"无关"
- 保持原文表述，不要编造内容
- 简洁输出，去除冗余

相关信息："""


async def compress_context(
    query: str,
    documents: List[Dict[str, Any]],
    chat_model: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    对检索结果进行上下文压缩，过滤无关内容。

    Args:
        query: 用户查询
        documents: 检索结果列表（dict 格式，含 document 字段）
        chat_model: LLM 实例，默认使用文本生成模型

    Returns:
        压缩后的文档列表（过滤掉完全无关的文档）
    """
    if not settings.CONTEXT_COMPRESSION_ENABLED:
        return documents

    if not documents:
        return documents

    if chat_model is None:
        from app.langchain_integration.models import MultimodalChatModel
        chat_model = MultimodalChatModel(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            model_name=settings.LLM_MODEL_NAME,
            temperature=0.0,
        )

    compressed = []
    for doc in documents:
        doc_text = doc.get("document", "")
        if not doc_text or len(doc_text) < 50:
            # 短文本不压缩
            compressed.append(doc)
            continue

        prompt = COMPRESSION_PROMPT.format(query=query, document=doc_text[:2000])

        try:
            from langchain_core.messages import HumanMessage
            result = await chat_model._agenerate([[HumanMessage(content=prompt)]])
            extracted = result.generations[0][0].text.strip()

            if extracted and "无关" not in extracted[:5]:
                new_doc = dict(doc)
                new_doc["document"] = extracted
                compressed.append(new_doc)
            else:
                logger.debug(f"[Compression] 过滤无关文档: {doc.get('id', 'unknown')}")
        except Exception as e:
            logger.warning(f"[Compression] 压缩失败，保留原文: {e}")
            compressed.append(doc)

    logger.info(f"[Compression] {len(documents)} → {len(compressed)} 篇文档")
    return compressed
