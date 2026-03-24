"""
Proposed 方法：MLLM 结构化描述 + 文本检索。

离线评测时，我们只关心基于文本描述的检索性能，因此这里直接复用
后端的向量检索逻辑，对文本 Query 执行检索，返回预测图像 ID 列表。

过滤条件：只检索 source_dataset 为 coco_val2017 的图片，
排除 PDF 上传图片对评估结果的干扰。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

# 将 backend 加入路径，以便直接导入 app 模块
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.langchain_integration.vectorstores import get_coco_proposed_vector_store  # noqa: E402

# 只检索 COCO 数据集图片，排除 PDF 提取图片的干扰
_COCO_FILTER = {"source_dataset": "coco_val2017"}


def retrieve(query: str, top_k: int = 10) -> List[str]:
    vs = get_coco_proposed_vector_store()
    results = vs.similarity_search_with_score(query, k=top_k, filter=_COCO_FILTER)
    return [doc.metadata.get("id", "") for doc, _score in results]
