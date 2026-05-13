"""
一次性回填 UniDoc energy 领域 proposed 缓存脚本。

功能概述：
    在早期实验阶段，energy 领域的 proposed 方法曾直接将 MLLM 生成的图片描述
    写入 ChromaDB（unidoc_energy_proposed 集合），但没有同步写入本地 JSONL 缓存文件。
    后续引入的 resume/build-index 流程依赖本地缓存文件来避免重复调用 MLLM API。

    本脚本的作用是从 ChromaDB 中读取已有描述，重建出与
    `evaluation.methods.unidoc_proposed.build_index()` 兼容的 JSONL 缓存文件，
    使后续操作可以正确 resume，不再重复调用 MLLM。

数据流向：
    ChromaDB (unidoc_energy_proposed)  →  本脚本  →  JSONL 缓存文件
                                              ↓
                                    build_index() 读取缓存 → 避免 MLLM 调用

缓存文件格式（JSONL，每行一条记录）：
    {
        "dataset_name": "UniDoc-Bench-subset",
        "domain": "energy",
        "model_name": "qwen-vl-xxx",
        "prompt_hash": "...",          # prompt 模板的 SHA256
        "generation_config_hash": "...", # 生成参数的 SHA256
        "image_id": "uuid",
        "file_hash": "...",            # 原始图片文件的 SHA256
        "file_path": "data/UniDoc-Bench-subset/energy/xxx.jpg",
        "description": "MLLM 生成的描述文本",
        "status": "success",
        "error": null,
        "attempt_count": 1,
        "updated_at": "2026-xx-xxTxx:xx:xxZ"
    }

使用示例（从项目根目录）：

    # 标准回填（如果缓存文件已存在会报错）
    python -m evaluation.backfill_unidoc_energy_cache

    # 强制覆盖已有缓存文件
    python -m evaluation.backfill_unidoc_energy_cache --force-overwrite

注意事项：
    - 本脚本是一次性迁移工具，仅处理 energy 领域
    - 回填的 attempt_count 统一为 1，updated_at 为当前 UTC 时间
    - ChromaDB 集合中的 ID 必须是 energy 候选集的子集，否则报错
    - 候选集中有图片在 ChromaDB 中缺失时会发出警告但不中断
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ──────────────────────────────────────────────────────────────────────
# 环境配置加载（同其他评测脚本）
# ──────────────────────────────────────────────────────────────────────
_env_path = PROJECT_ROOT / "backend" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# ──────────────────────────────────────────────────────────────────────
# 导入依赖
# ──────────────────────────────────────────────────────────────────────
from evaluation.datasets.unidoc_subset import get_domain_image_records  # noqa: E402
from evaluation.methods.unidoc_proposed import (  # noqa: E402
    _client,                    # ChromaDB 客户端实例
    _collection_name,           # 根据 domain 生成 ChromaDB 集合名（如 "unidoc_energy_proposed"）
    _resolve_cache_file,        # 根据参数计算缓存文件路径
    _sha256_file,               # 计算文件的 SHA256 哈希
    _sha256_text,               # 计算文本的 SHA256 哈希
    _stable_hash,               # 计算字典的稳定哈希（用于 generation_config）
    _utc_now_iso,               # 获取当前 UTC 时间的 ISO 格式字符串
)
from app.langchain_integration.chains import get_image_description_chain  # noqa: E402

# ──────────────────────────────────────────────────────────────────────
# 常量配置
# ──────────────────────────────────────────────────────────────────────
# ---- 常量配置 ----

DOMAIN = "energy"                                      # 固定处理 energy 领域
DEFAULT_SUBSET_ROOT = "data/UniDoc-Bench-subset"       # 数据集根目录
DEFAULT_DATASET_NAME = "UniDoc-Bench-subset"           # 数据集标识名
DEFAULT_CACHE_DIR = "data/cache/unidoc_proposed"       # 缓存输出目录


# ──────────────────────────────────────────────────────────────────────
# 路径处理工具函数
# ──────────────────────────────────────────────────────────────────────

def _to_cache_style_path(path: str | Path) -> str:
    """将路径中的正斜杠转为反斜杠，与 Windows 缓存文件格式保持一致。"""
    return str(path).replace("/", "\\")


def _project_relative_cache_path(path: str | Path) -> str:
    """将绝对路径转为项目相对路径（Windows 反斜杠格式）。

    如果路径不在项目根目录下，保持原样返回。
    用于缓存文件中的 file_path 字段，确保跨机器可移植。
    """
    path = Path(path)
    if path.is_absolute():
        try:
            return _to_cache_style_path(path.relative_to(PROJECT_ROOT))
        except ValueError:
            return _to_cache_style_path(path)
    return _to_cache_style_path(path)


# ──────────────────────────────────────────────────────────────────────
# ChromaDB 数据读取
# ──────────────────────────────────────────────────────────────────────

def _load_collection_rows() -> List[Dict[str, Any]]:
    """从 ChromaDB 的 unidoc_energy_proposed 集合中读取全部记录。

    每条记录包含 image_id、description（MLLM 生成的描述文本）和 metadata。
    会校验：集合非空、三个列表长度一致、ID 无重复。

    Returns:
        包含 {"image_id", "description", "metadata"} 字典的列表。
    """
    collection_name = _collection_name(DOMAIN)  # → "unidoc_energy_proposed"
    collection = _client.get_collection(name=collection_name)
    # include 指定只拉取 documents 和 metadatas（embeddings 不需要）
    payload = collection.get(include=["documents", "metadatas"])

    ids = payload.get("ids") or []
    documents = payload.get("documents") or []
    metadatas = payload.get("metadatas") or []

    # ── 数据完整性校验 ──
    if not ids:
        raise RuntimeError(f"Collection '{collection_name}' is empty; nothing to backfill.")
    if not (len(ids) == len(documents) == len(metadatas)):
        raise RuntimeError(
            f"Collection '{collection_name}' returned mismatched lengths: "
            f"ids={len(ids)}, documents={len(documents)}, metadatas={len(metadatas)}"
        )
    if len(set(str(i) for i in ids)) != len(ids):
        raise RuntimeError(f"Collection '{collection_name}' contains duplicate ids; aborting backfill.")

    rows: List[Dict[str, Any]] = []
    for image_id, description, metadata in zip(ids, documents, metadatas):
        rows.append({
            "image_id": str(image_id),
            "description": "" if description is None else str(description),
            "metadata": metadata if isinstance(metadata, dict) else {},
        })
    return rows


# ──────────────────────────────────────────────────────────────────────
# 数据集映射构建
# ──────────────────────────────────────────────────────────────────────

def _build_dataset_maps(subset_root: Path) -> tuple[Dict[str, str], Dict[str, str]]:
    """构建 image_id → 文件路径的映射。

    返回两个字典：
    - abs_map: image_id → 绝对路径（用于计算 file_hash）
    - rel_map: image_id → 项目相对路径（用于缓存文件中的 file_path 字段）
    """
    records = get_domain_image_records(DOMAIN, subset_root)
    abs_map: Dict[str, str] = {}
    rel_map: Dict[str, str] = {}
    for record in records:
        image_id = str(record["id"])
        abs_path = str(Path(record["file_path"]).resolve())
        abs_map[image_id] = abs_path
        # rel_map 使用 subset_root/{image_id} 格式（与 build_index 保持一致）
        rel_map[image_id] = _project_relative_cache_path(subset_root / image_id)
    return abs_map, rel_map


# ──────────────────────────────────────────────────────────────────────
# 缓存签名构建
# ──────────────────────────────────────────────────────────────────────

def _build_signature(dataset_name: str) -> Dict[str, str]:
    """构建缓存文件的运行签名，用于校验缓存是否与当前配置匹配。

    签名包含：dataset_name、domain、model_name、prompt_hash、generation_config_hash。
    当 prompt 或模型配置变化时，hash 会不同，导致缓存自动失效。
    """
    chain = get_image_description_chain()
    chat_model = chain.chat_model
    return {
        "dataset_name": dataset_name,
        "domain": DOMAIN,
        "model_name": chat_model.model_name or "",
        "prompt_hash": _sha256_text(chain.prompt),
        "generation_config_hash": _stable_hash({
            "base_url": chat_model.base_url or "",
            "temperature": chat_model.temperature,
            "max_tokens": chat_model.max_tokens,
        }),
    }


def _resolve_record_file_path(metadata: Dict[str, Any], fallback_rel_path: str) -> str:
    """从 metadata 中提取 file_path，若缺失则使用 fallback 路径。

    ChromaDB metadata 中的 file_path 可能与数据集中的路径格式不一致，
    因此优先使用 metadata 中的值，但最终会与数据集路径做对比。
    """
    metadata_file_path = str(metadata.get("file_path", "")).strip()
    if not metadata_file_path:
        return fallback_rel_path
    return _project_relative_cache_path(metadata_file_path)


def backfill_energy_cache(
    *,
    subset_root: str,
    dataset_name: str,
    cache_dir: str,
    force_overwrite: bool,
) -> Path:
    """执行 energy 领域 proposed 缓存的回填操作。

    主要流程：
    1. 检查目标缓存文件是否已存在（存在则需 --force-overwrite）
    2. 从 ChromaDB 读取已有描述记录
    3. 从数据集加载 energy 领域的候选图片元数据
    4. 校验 ChromaDB 中的 ID 必须是候选集的子集（不能有越界 ID）
    5. 构建缓存签名（model_name、prompt_hash 等），用于后续缓存有效性校验
    6. 逐条生成缓存记录并写入 JSONL 文件

    Args:
        subset_root: 数据集根目录路径。
        dataset_name: 数据集标识名（用于缓存签名和文件路径）。
        cache_dir: 缓存文件输出目录。
        force_overwrite: 是否覆盖已存在的缓存文件。

    Returns:
        写入的缓存文件路径。
    """
    subset_root_path = Path(subset_root)
    cache_root = Path(cache_dir)
    # 根据参数计算缓存文件路径，格式为 {cache_dir}/{dataset_name}_{domain}.jsonl
    cache_file = _resolve_cache_file(cache_root, dataset_name, DOMAIN)

    # ── 步骤 1：检查缓存文件是否已存在 ──
    if cache_file.exists() and not force_overwrite:
        raise FileExistsError(
            f"Target cache file already exists: {cache_file}. "
            "Use --force-overwrite to replace it."
        )

    # ── 步骤 2：从 ChromaDB 读取已有记录 ──
    rows = _load_collection_rows()

    # ── 步骤 3：从数据集加载候选图片元数据 ──
    dataset_abs_map, dataset_rel_map = _build_dataset_maps(subset_root_path)
    if not dataset_abs_map:
        raise RuntimeError(f"No energy image records found under subset root: {subset_root_path}")
    candidate_ids = set(dataset_abs_map)
    collection_ids = {row["image_id"] for row in rows}

    # ── 步骤 4：ID 一致性校验 ──
    # ChromaDB 中的 ID 必须是候选集的子集，否则说明数据不一致
    extra_ids = sorted(collection_ids - candidate_ids)
    if extra_ids:
        preview = ", ".join(extra_ids[:5])
        suffix = " ..." if len(extra_ids) > 5 else ""
        raise RuntimeError(
            f"Collection contains {len(extra_ids)} id(s) outside energy candidate set: {preview}{suffix}"
        )

    # 候选集中有图片在 ChromaDB 中缺失是可接受的（可能生成失败或尚未处理）
    missing_ids = sorted(candidate_ids - collection_ids)
    if missing_ids:
        print(
            f"[WARN] Energy candidate set has {len(missing_ids)} image(s) missing from collection. "
            "Only existing successful collection records will be backfilled."
        )

    # ── 步骤 5：构建缓存签名 ──
    # 签名用于后续 build_index() 时校验缓存是否与当前模型/prompt 配置匹配
    signature = _build_signature(dataset_name)
    updated_at = _utc_now_iso()

    # ── 步骤 6：逐条生成缓存记录 ──
    cache_records: List[Dict[str, Any]] = []
    mismatched_metadata_paths = 0
    for row in sorted(rows, key=lambda item: item["image_id"]):
        image_id = row["image_id"]
        # 跳过不在候选集中的 ID（理论上不会发生，防御性检查）
        if image_id not in dataset_abs_map:
            continue

        abs_path = dataset_abs_map[image_id]
        fallback_rel_path = dataset_rel_map[image_id]
        # 优先使用 metadata 中的 file_path，但最终会用 fallback 路径标准化
        resolved_file_path = _resolve_record_file_path(row["metadata"], fallback_rel_path)

        if resolved_file_path != fallback_rel_path:
            mismatched_metadata_paths += 1

        # 构建与 build_index() 输出格式完全一致的缓存记录
        cache_records.append({
            **signature,                    # dataset_name, domain, model_name, prompt_hash 等
            "image_id": image_id,
            "file_hash": _sha256_file(abs_path),  # 对原始图片文件计算哈希
            "file_path": fallback_rel_path,        # 使用数据集相对路径（标准化）
            "description": row["description"],     # 从 ChromaDB 读取的描述文本
            "status": "success",                   # 回填的记录视为成功
            "error": None,
            "attempt_count": 1,                    # 回填记录统一标记为 1 次尝试
            "updated_at": updated_at,              # 统一使用当前 UTC 时间
        })

    if not cache_records:
        raise RuntimeError("No cache records were reconstructed; aborting write.")

    # ── 写入 JSONL 文件 ──
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with cache_file.open("w", encoding="utf-8") as f:
        for record in cache_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ── 输出回填统计信息 ──
    print(f"Collection rows loaded: {len(rows)}")
    print(f"Energy candidate images: {len(candidate_ids)}")
    print(f"Backfilled cache records: {len(cache_records)}")
    print(f"Target cache file: {cache_file}")
    print(
        "Run signature: "
        f"dataset={signature['dataset_name']}  "
        f"domain={signature['domain']}  "
        f"model={signature['model_name']}  "
        f"prompt_hash={signature['prompt_hash'][:12]}  "      # 只显示前 12 字符
        f"generation_config_hash={signature['generation_config_hash'][:12]}"
    )
    if mismatched_metadata_paths:
        print(
            f"[INFO] Ignored {mismatched_metadata_paths} metadata file_path value(s) and normalized to dataset-relative cache paths."
        )
    print("[INFO] attempt_count is backfilled as 1 for all records.")
    print(f"[INFO] updated_at is backfilled as current UTC time: {updated_at}")

    return cache_file


def main() -> None:
    """命令行入口：解析参数并执行回填。"""
    # ---- 命令行参数解析 ----
    parser = argparse.ArgumentParser(
        description="Backfill UniDoc energy proposed cache from the existing Chroma collection."
    )
    parser.add_argument("--subset-root", type=str, default=DEFAULT_SUBSET_ROOT,
                        help="数据集根目录")
    parser.add_argument("--dataset-name", type=str, default=DEFAULT_DATASET_NAME,
                        help="数据集标识名（用于缓存签名）")
    parser.add_argument("--cache-dir", type=str, default=DEFAULT_CACHE_DIR,
                        help="缓存文件输出目录")
    parser.add_argument("--force-overwrite", action="store_true",
                        help="覆盖已存在的缓存文件")
    args = parser.parse_args()

    cache_file = backfill_energy_cache(
        subset_root=args.subset_root,
        dataset_name=args.dataset_name,
        cache_dir=args.cache_dir,
        force_overwrite=args.force_overwrite,
    )
    print(f"[DONE] Energy proposed cache backfilled to: {cache_file}")


if __name__ == "__main__":
    main()
