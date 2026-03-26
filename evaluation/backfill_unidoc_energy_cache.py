"""
一次性回填 UniDoc energy proposed 缓存。

用途：从现有的 `unidoc_energy_proposed` Chroma collection 中读取已经生成好的
描述文本，并补写为与 `evaluation.methods.unidoc_proposed.build_index()`
兼容的本地 JSONL 缓存文件，避免后续 resume/build-index 时重新调用 MLLM。

示例：
    python -m evaluation.backfill_unidoc_energy_cache
    python -m evaluation.backfill_unidoc_energy_cache --force-overwrite
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 加载 backend/.env，与 run_unidoc_eval.py 保持一致，确保配置可用。
_env_path = PROJECT_ROOT / "backend" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from evaluation.datasets.unidoc_subset import get_domain_image_records  # noqa: E402
from evaluation.methods.unidoc_proposed import (  # noqa: E402
    _client,
    _collection_name,
    _resolve_cache_file,
    _sha256_file,
    _sha256_text,
    _stable_hash,
    _utc_now_iso,
)
from app.langchain_integration.chains import get_image_description_chain  # noqa: E402

DOMAIN = "energy"
DEFAULT_SUBSET_ROOT = "data/UniDoc-Bench-subset"
DEFAULT_DATASET_NAME = "UniDoc-Bench-subset"
DEFAULT_CACHE_DIR = "data/cache/unidoc_proposed"


def _to_cache_style_path(path: str | Path) -> str:
    return str(path).replace("/", "\\")


def _project_relative_cache_path(path: str | Path) -> str:
    path = Path(path)
    if path.is_absolute():
        try:
            return _to_cache_style_path(path.relative_to(PROJECT_ROOT))
        except ValueError:
            return _to_cache_style_path(path)
    return _to_cache_style_path(path)


def _load_collection_rows() -> List[Dict[str, Any]]:
    collection_name = _collection_name(DOMAIN)
    collection = _client.get_collection(name=collection_name)
    payload = collection.get(include=["documents", "metadatas"])

    ids = payload.get("ids") or []
    documents = payload.get("documents") or []
    metadatas = payload.get("metadatas") or []

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


def _build_dataset_maps(subset_root: Path) -> tuple[Dict[str, str], Dict[str, str]]:
    records = get_domain_image_records(DOMAIN, subset_root)
    abs_map: Dict[str, str] = {}
    rel_map: Dict[str, str] = {}
    for record in records:
        image_id = str(record["id"])
        abs_path = str(Path(record["file_path"]).resolve())
        abs_map[image_id] = abs_path
        rel_map[image_id] = _project_relative_cache_path(subset_root / image_id)
    return abs_map, rel_map


def _build_signature(dataset_name: str) -> Dict[str, str]:
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
    subset_root_path = Path(subset_root)
    cache_root = Path(cache_dir)
    cache_file = _resolve_cache_file(cache_root, dataset_name, DOMAIN)

    if cache_file.exists() and not force_overwrite:
        raise FileExistsError(
            f"Target cache file already exists: {cache_file}. "
            "Use --force-overwrite to replace it."
        )

    rows = _load_collection_rows()
    dataset_abs_map, dataset_rel_map = _build_dataset_maps(subset_root_path)
    if not dataset_abs_map:
        raise RuntimeError(f"No energy image records found under subset root: {subset_root_path}")
    candidate_ids = set(dataset_abs_map)
    collection_ids = {row["image_id"] for row in rows}

    extra_ids = sorted(collection_ids - candidate_ids)
    if extra_ids:
        preview = ", ".join(extra_ids[:5])
        suffix = " ..." if len(extra_ids) > 5 else ""
        raise RuntimeError(
            f"Collection contains {len(extra_ids)} id(s) outside energy candidate set: {preview}{suffix}"
        )

    missing_ids = sorted(candidate_ids - collection_ids)
    if missing_ids:
        print(
            f"[WARN] Energy candidate set has {len(missing_ids)} image(s) missing from collection. "
            "Only existing successful collection records will be backfilled."
        )

    signature = _build_signature(dataset_name)
    updated_at = _utc_now_iso()

    cache_records: List[Dict[str, Any]] = []
    mismatched_metadata_paths = 0
    for row in sorted(rows, key=lambda item: item["image_id"]):
        image_id = row["image_id"]
        if image_id not in dataset_abs_map:
            continue

        abs_path = dataset_abs_map[image_id]
        fallback_rel_path = dataset_rel_map[image_id]
        resolved_file_path = _resolve_record_file_path(row["metadata"], fallback_rel_path)

        if resolved_file_path != fallback_rel_path:
            mismatched_metadata_paths += 1

        cache_records.append({
            **signature,
            "image_id": image_id,
            "file_hash": _sha256_file(abs_path),
            "file_path": fallback_rel_path,
            "description": row["description"],
            "status": "success",
            "error": None,
            "attempt_count": 1,
            "updated_at": updated_at,
        })

    if not cache_records:
        raise RuntimeError("No cache records were reconstructed; aborting write.")

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with cache_file.open("w", encoding="utf-8") as f:
        for record in cache_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Collection rows loaded: {len(rows)}")
    print(f"Energy candidate images: {len(candidate_ids)}")
    print(f"Backfilled cache records: {len(cache_records)}")
    print(f"Target cache file: {cache_file}")
    print(
        "Run signature: "
        f"dataset={signature['dataset_name']}  "
        f"domain={signature['domain']}  "
        f"model={signature['model_name']}  "
        f"prompt_hash={signature['prompt_hash'][:12]}  "
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
    parser = argparse.ArgumentParser(
        description="Backfill UniDoc energy proposed cache from the existing Chroma collection."
    )
    parser.add_argument("--subset-root", type=str, default=DEFAULT_SUBSET_ROOT)
    parser.add_argument("--dataset-name", type=str, default=DEFAULT_DATASET_NAME)
    parser.add_argument("--cache-dir", type=str, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--force-overwrite", action="store_true")
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
