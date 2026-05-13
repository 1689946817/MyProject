"""
UniDoc-Bench 完整数据集加载器。

本模块提供 UniDoc-Bench 全量数据集（每领域 200 条 QA）的加载与查询接口。
UniDoc-Bench 是一个多领域文档理解基准测试集，覆盖 8 个领域。

数据集结构：
  data/UniDoc-Bench/
  ├── data/{domain}-00000-of-00001.parquet   # 每领域 200 条 QA（Parquet 格式）
  └── images/{domain}/{doc_id}/{doc_id}_page_{NNNN}.png

ID 体系：使用图片相对路径字符串作为文档 ID，
例如 `images/finance/6002966/6002966_page_0009.png`。

与 unidoc_subset.py 的区别：
  - 本模块加载 data/UniDoc-Bench/（200 条/领域）
  - unidoc_subset 加载 data/UniDoc-Bench-subset/（100 条/领域）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Set

# ---- 领域定义 ----
# UniDoc-Bench 覆盖的 8 个领域，与数据集 Parquet 文件名对应
DOMAINS = [
    "commerce_manufacturing",  # 商业制造
    "construction",            # 建筑工程
    "crm",                     # 客户关系管理
    "education",               # 教育
    "energy",                  # 能源
    "finance",                 # 金融
    "healthcare",              # 医疗健康
    "legal",                   # 法律
]


@dataclass
class UniDocQuerySample:
    """UniDoc 查询样本数据类。

    每条样本代表一个带标准答案的文档问答任务。

    属性:
        query: 用户查询/问题文本
        relevant_ids: 标准答案相关的图片相对路径集合（ground truth）
        domain: 所属领域（如 "finance"）
        question_type: 问题类型（如 "factoid"、"list"）
        answer_type: 答案类型（如 "extractive"、"abstractive"）
        answer: 标准答案文本
    """
    query: str
    relevant_ids: Set[str]
    domain: str
    question_type: str
    answer_type: str
    answer: str = ""


def load_unidoc_domain(domain: str, dataset_root: str | Path) -> List[UniDocQuerySample]:
    """加载指定领域的 QA 样本。

    从 Parquet 文件中读取原始数据，解析 gt_image_paths 作为标准答案相关图片。

    Args:
        domain: 领域名称（如 "finance"），对应 Parquet 文件名前缀。
        dataset_root: 数据集根目录，下级应有 data/ 子目录。

    Returns:
        该领域的所有查询样本列表。

    Raises:
        FileNotFoundError: 对应的 Parquet 文件不存在时抛出。
    """
    import pandas as pd

    dataset_root = Path(dataset_root)
    parquet_path = dataset_root / "data" / f"{domain}-00000-of-00001.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet not found: {parquet_path}")

    df = pd.read_parquet(parquet_path)
    samples: List[UniDocQuerySample] = []
    for _, row in df.iterrows():
        # gt_image_paths 存储标准答案相关的文档图片路径
        gt_paths = row.get("gt_image_paths", [])
        if gt_paths is None:
            gt_paths = []
        relevant_ids = {str(p) for p in gt_paths}
        samples.append(UniDocQuerySample(
            query=str(row["question"]),
            relevant_ids=relevant_ids,
            domain=str(row.get("domain", domain)),  # 若 Parquet 中无 domain 字段，使用参数值
            question_type=str(row.get("question_type", "")),
            answer_type=str(row.get("answer_type", "")),
            answer=str(row.get("answer", "")),
        ))
    return samples


def get_domain_image_records(domain: str, dataset_root: str | Path) -> List[dict]:
    """返回该领域完整候选集的图像记录列表。

    候选集 = 该域所有 query 的 longdoc_image_paths 并集（去重，只含磁盘实际存在的文件）。
    用于向量化索引构建阶段，确保所有可检索的图片都被纳入 ChromaDB。

    Args:
        domain: 领域名称。
        dataset_root: 数据集根目录。

    Returns:
        图像记录列表，每项为 {"id": 相对路径, "file_path": 绝对路径}。
        按 id 字典序排列，保证可复现。
    """
    import pandas as pd

    dataset_root = Path(dataset_root)
    parquet_path = dataset_root / "data" / f"{domain}-00000-of-00001.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet not found: {parquet_path}")

    df = pd.read_parquet(parquet_path)
    # 收集该领域所有文档的图片路径（longdoc_image_paths 包含文档中的全部页面图片）
    all_rel_paths: Set[str] = set()
    for _, row in df.iterrows():
        longdoc_paths = row.get("longdoc_image_paths", [])
        if longdoc_paths is not None:
            for p in longdoc_paths:
                all_rel_paths.add(str(p))

    # 仅保留磁盘上实际存在的文件
    records = []
    for rel_path in sorted(all_rel_paths):
        abs_path = dataset_root / rel_path
        if abs_path.exists():
            records.append({"id": rel_path, "file_path": str(abs_path)})
        else:
            print(f"[SKIP] Image not found on disk: {abs_path}")

    return records
