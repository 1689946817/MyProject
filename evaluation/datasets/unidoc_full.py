"""
UniDoc-Bench 完整数据集加载器。

数据集结构：
  data/UniDoc-Bench/
  ├── data/{domain}-00000-of-00001.parquet   # 每领域 200 条 QA
  └── images/{domain}/{doc_id}/{doc_id}_page_{NNNN}.png

ID 体系：使用图片相对路径字符串作为文档 ID，
例如 `images/finance/6002966/6002966_page_0009.png`。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Set

DOMAINS = [
    "commerce_manufacturing",
    "construction",
    "crm",
    "education",
    "energy",
    "finance",
    "healthcare",
    "legal",
]


@dataclass
class UniDocQuerySample:
    query: str
    relevant_ids: Set[str]
    domain: str
    question_type: str
    answer_type: str
    answer: str = ""


def load_unidoc_domain(domain: str, dataset_root: str | Path) -> List[UniDocQuerySample]:
    """加载指定领域的 QA 样本。"""
    import pandas as pd

    dataset_root = Path(dataset_root)
    parquet_path = dataset_root / "data" / f"{domain}-00000-of-00001.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet not found: {parquet_path}")

    df = pd.read_parquet(parquet_path)
    samples: List[UniDocQuerySample] = []
    for _, row in df.iterrows():
        gt_paths = row.get("gt_image_paths", [])
        if gt_paths is None:
            gt_paths = []
        relevant_ids = {str(p) for p in gt_paths}
        samples.append(UniDocQuerySample(
            query=str(row["question"]),
            relevant_ids=relevant_ids,
            domain=str(row.get("domain", domain)),
            question_type=str(row.get("question_type", "")),
            answer_type=str(row.get("answer_type", "")),
            answer=str(row.get("answer", "")),
        ))
    return samples


def get_domain_image_records(domain: str, dataset_root: str | Path) -> List[dict]:
    """
    返回该领域完整候选集的图像记录列表。

    候选集 = 该域所有 query 的 longdoc_image_paths 并集（去重，只含磁盘存在的文件）。
    每条记录：{"id": 相对路径, "file_path": 绝对路径}
    """
    import pandas as pd

    dataset_root = Path(dataset_root)
    parquet_path = dataset_root / "data" / f"{domain}-00000-of-00001.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet not found: {parquet_path}")

    df = pd.read_parquet(parquet_path)
    all_rel_paths: Set[str] = set()
    for _, row in df.iterrows():
        longdoc_paths = row.get("longdoc_image_paths", [])
        if longdoc_paths is not None:
            for p in longdoc_paths:
                all_rel_paths.add(str(p))

    records = []
    for rel_path in sorted(all_rel_paths):
        abs_path = dataset_root / rel_path
        if abs_path.exists():
            records.append({"id": rel_path, "file_path": str(abs_path)})
        else:
            print(f"[SKIP] Image not found on disk: {abs_path}")

    return records
