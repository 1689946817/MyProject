"""
Proposed 方法的离线检索接口。

本方法的核心思路：用 MLLM 将图片"翻译"为结构化文本描述，
然后基于文本描述进行向量检索（文本→图像）。

离线评测时，我们只关心基于文本描述的检索性能，因此这里直接复用
后端 LangChain 的向量检索逻辑，对文本 Query 执行相似度检索，
返回预测图像 ID 列表。

过滤条件：只检索 source_dataset 为 coco_val2017 的图片，
排除 PDF 上传图片等非评估数据对结果的干扰。

ChromaDB 集合：images_coco_proposed（由后端向量库模块管理）。
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
    """使用 Proposed 方法检索图像。

    将查询文本通过 Embedding 模型编码后，在 ChromaDB 向量库中
    执行余弦相似度检索，返回 top_k 个最相关的图像 ID。

    Args:
        query: 查询文本（来自评估数据集的问题）。
        top_k: 返回的检索结果数量，默认 10。

    Returns:
        List[str]: top_k 个预测图像 ID 列表，按相似度降序排列。
    """
    vs = get_coco_proposed_vector_store()
    results = vs.similarity_search_with_score(query, k=top_k, filter=_COCO_FILTER)
    return [doc.metadata.get("id", "") for doc, _score in results]
