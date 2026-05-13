"""
MS-COCO 子集数据加载器。

本模块提供 COCO 评测子集的加载接口，用于图像检索和 RAG 问答评估。
数据集为预处理后的 JSON 文件，包含查询文本、相关图像 ID 和可选的参考答案。

JSON 数据格式（每行一个对象，或整个文件为数组）：
{
  "query": "a child playing football on the grass",
  "relevant_ids": ["000000123456", "000000234567"],
  "reference_answer": "A child is playing football on the grass."  // 可选
}

字段说明：
- query: 用户查询/问题文本
- relevant_ids: 与该查询相关的图像 ID 列表，对应系统中 ImageRecord 的 id（UUID 字符串）
- reference_answer: 可选的标准答案，用于 Answer Correctness 指标评估
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set


@dataclass
class CocoQuerySample:
    """COCO 查询样本数据类。

    属性:
        query: 用户查询/问题文本
        relevant_ids: 与查询相关的图像 ID 集合（用于检索评估）
        reference_answer: 可选的标准答案（用于生成质量评估）
    """
    query: str
    relevant_ids: Set[str]
    reference_answer: str = ""


def load_coco_subset(json_path: str | Path) -> List[CocoQuerySample]:
    """加载 COCO 评测子集。

    从 JSON 文件中读取预处理好的查询样本，解析为 CocoQuerySample 列表。

    Args:
        json_path: JSON 文件路径，内容应为对象数组。

    Returns:
        所有查询样本的列表。
    """
    path = Path(json_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    samples: List[CocoQuerySample] = []
    for item in raw:
        query = item["query"]
        rel_ids = set(item.get("relevant_ids", []))
        reference_answer = item.get("reference_answer", "")
        samples.append(CocoQuerySample(query=query, relevant_ids=rel_ids, reference_answer=reference_answer))
    return samples

