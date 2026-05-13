"""
OCR-Text-RAG 基线方法。

用 OCR 文字向量检索图片（与 baseline_ocr 共享相同的 OCR 索引），
但生成阶段只将 OCR 识别出的文字作为上下文传给 LLM，不传原始图片。

对比实验设计：
- baseline_ocr_rag：用 OCR 检索 → 传原始图片给 LLM
- ocr_text_rag（本文件）：用 OCR 检索 → 传 OCR 文字给 LLM

用途：验证"OCR 文字作为上下文"与"原始图片作为上下文"的生成质量差异。
如果 OCR 文字方法效果明显差于传原始图片，说明原始图片中包含了
OCR 未提取的视觉语义信息（如布局、图表、颜色等）。

返回格式：
    {
        "generated_answer": str,   # LLM 生成的回答
        "context": str,            # 拼接的 OCR 文字
        "images": [],              # 不传图片，列表为空
    }
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.core.config import settings  # noqa: E402
from app.langchain_integration.models import get_chat_model, get_embedding_model  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402

# 初始化持久化 ChromaDB 客户端，使用与后端相同的存储目录
_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)
# 使用 OCR 基线构建的向量集合（与 baseline_ocr_rag 共享）
_collection = _client.get_or_create_collection(name="images_ocr_text")

# 提示词模板：要求 LLM 仅基于 OCR 文字回答，信息不足时明确说明
_PROMPT = (
    "你是一个多模态知识库问答助手。以下是从知识库中检索到的图像 OCR 文字信息，"
    "请基于这些文字内容回答用户的问题。\n\n"
    "检索到的 OCR 文字：\n{context}\n\n"
    "用户问题：{query}\n\n"
    "请基于以上内容进行回答，如果信息不足以回答某些部分，请明确说明不确定。"
)


def retrieve(query: str, top_k: int = 5) -> List[Dict[str, str]]:
    """
    用 OCR 文字向量检索，返回 (id, ocr_text) 列表。

    Returns:
        List[dict]: [{"id": str, "ocr_text": str}, ...]
    """
    embedder = get_embedding_model()
    emb = embedder.embed_query(query)
    results = _collection.query(query_embeddings=[emb], n_results=top_k, include=["documents", "metadatas"])
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    return [{"id": str(i), "ocr_text": t} for i, t in zip(ids, docs)]


async def generate(query: str, top_k: int = 5, extra_context: Optional[str] = None) -> Dict[str, Any]:
    """
    检索 OCR 文字，将 OCR 文字作为上下文传给 LLM（不传图片）。

    Args:
        query: 用户问题
        top_k: 检索数量
        extra_context: 来自文本知识库的额外上下文（多模态文档场景）

    Returns:
        dict: {
            "generated_answer": str,
            "context": str,   # 拼接的 OCR 文字
            "images": [],     # 不传图片
        }
    """
    hits = retrieve(query, top_k=top_k)
    ocr_texts = [h["ocr_text"] for h in hits if h["ocr_text"]]

    context_parts = ocr_texts
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
