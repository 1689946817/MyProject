"""
MS-COCO 子集数据加载与抽象。

为了简化实现，这里假设你已经将需要评测的子集预处理为一个 JSON 文件，
每一行（或列表元素）形如：

{
  "query": "a child playing football on the grass",
  "relevant_ids": ["000000123456", "000000234567"]
}

其中 relevant_ids 与系统中向量库 / ImageRecord 的 id 对应。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set


@dataclass
class CocoQuerySample:
    query: str
    relevant_ids: Set[str]


def load_coco_subset(json_path: str | Path) -> List[CocoQuerySample]:
    path = Path(json_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    samples: List[CocoQuerySample] = []
    for item in raw:
        query = item["query"]
        rel_ids = set(item.get("relevant_ids", []))
        samples.append(CocoQuerySample(query=query, relevant_ids=rel_ids))
    return samples

