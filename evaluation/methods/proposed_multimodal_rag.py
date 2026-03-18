"""
Proposed 方法：MLLM 结构化描述 + 文本检索。

离线评测时，我们只关心基于文本描述的检索性能，因此这里直接复用
后端的向量检索逻辑，对文本 Query 执行检索，返回预测图像 ID 列表。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

# 将 backend 加入路径，以便直接导入 app 模块
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.langchain_integration.vectorstores import get_vector_store  # noqa: E402


def retrieve(query: str, top_k: int = 10) -> List[str]:
    hits = get_vector_store().search_by_text(query_text=query, top_k=top_k)
    return [str(item["id"]) for item in hits]

