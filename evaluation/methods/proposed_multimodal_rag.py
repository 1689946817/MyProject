"""
Proposed 方法：MLLM 结构化描述 + 文本检索。

离线评测时，我们只关心基于文本描述的检索性能，因此这里直接复用
后端的向量检索逻辑，对文本 Query 执行检索，返回预测图像 ID 列表。
"""

from __future__ import annotations

from typing import List

from backend.app.retrieval.vector_store import search_by_text


def retrieve(query: str, top_k: int = 10) -> List[str]:
    hits = search_by_text(query_text=query, top_k=top_k)
    return [str(item["id"]) for item in hits]

