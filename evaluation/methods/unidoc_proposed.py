"""
UniDoc-Bench Proposed 方法：MLLM 描述 + 文本向量检索。

集合命名：unidoc_{domain}_proposed
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

import chromadb
from chromadb.config import Settings as ChromaSettings
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.langchain_integration.chains import get_image_description_chain  # noqa: E402
from app.langchain_integration.models import get_embedding_model, guess_image_mime_type  # noqa: E402

_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)


def _collection_name(domain: str) -> str:
    return f"unidoc_{domain}_proposed"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(file_path: str) -> str:
    digest = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_hash(payload: Dict[str, Any]) -> str:
    return _sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resolve_cache_file(cache_dir: str | Path, dataset_name: str, domain: str) -> Path:
    return Path(cache_dir) / dataset_name / domain / "descriptions.jsonl"


def _estimate_base64_size(raw_size: int) -> int:
    return ((raw_size + 2) // 3) * 4


def _prepare_image_payload(
    file_path: str,
    *,
    max_base64_bytes: int = 9_500_000,
) -> tuple[str, str]:
    with open(file_path, "rb") as f:
        image_data = f.read()

    if _estimate_base64_size(len(image_data)) <= max_base64_bytes:
        return base64.b64encode(image_data).decode("utf-8"), guess_image_mime_type(file_path)

    print(
        f"[INFO] Image payload exceeds limit, compressing before MLLM request: "
        f"{file_path} ({len(image_data) / 1024:.1f}KB)"
    )

    image = Image.open(BytesIO(image_data))
    if image.mode != "RGB":
        image = image.convert("RGB")

    max_side_candidates = [1800, 1600, 1280]
    quality_candidates = [85, 75, 65]

    for max_side in max_side_candidates:
        working = image.copy()
        longest_side = max(working.width, working.height)
        if longest_side > max_side:
            scale = max_side / longest_side
            working = working.resize(
                (
                    max(1, int(round(working.width * scale))),
                    max(1, int(round(working.height * scale))),
                ),
                Image.Resampling.LANCZOS,
            )

        for quality in quality_candidates:
            buffer = BytesIO()
            working.save(buffer, format="JPEG", quality=quality, optimize=True)
            candidate = buffer.getvalue()
            if _estimate_base64_size(len(candidate)) <= max_base64_bytes:
                print(
                    f"[INFO] Compressed image payload for MLLM: {file_path} -> "
                    f"{len(candidate) / 1024:.1f}KB (max_side={max_side}, quality={quality})"
                )
                return base64.b64encode(candidate).decode("utf-8"), "image/jpeg"

    raise ValueError(
        "Image exceeds multimodal payload limit even after resize/jpeg compression: "
        f"{file_path}"
    )


def _is_non_retryable_payload_error(error_message: str) -> bool:
    normalized = error_message.lower()
    if "400" not in normalized and "bad request" not in normalized:
        return False
    payload_markers = [
        "payload",
        "base64",
        "image",
        "file",
        "size",
        "too large",
        "limit",
        "content too long",
        "maximum context length",
    ]
    return any(marker in normalized for marker in payload_markers) or "bad request" in normalized


def _load_cache_records(cache_file: Path) -> List[Dict[str, Any]]:
    if not cache_file.exists():
        return []

    records: List[Dict[str, Any]] = []
    with cache_file.open("r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[WARN] Skip malformed cache line {line_no} in {cache_file}: {exc}")
                continue
            if isinstance(payload, dict):
                records.append(payload)
            else:
                print(f"[WARN] Skip non-object cache line {line_no} in {cache_file}")
    return records


def _append_cache_record(cache_file: Path, record: Dict[str, Any]) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with cache_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _build_records_by_image_id(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        image_id = str(record.get("image_id", "")).strip()
        if not image_id:
            continue
        grouped.setdefault(image_id, []).append(record)
    return grouped


def _identity_matches(cache_record: Dict[str, Any], current_identity: Dict[str, str]) -> bool:
    required_keys = [
        "dataset_name",
        "domain",
        "image_id",
        "file_hash",
        "model_name",
        "prompt_hash",
        "generation_config_hash",
    ]
    return all(str(cache_record.get(key, "")) == current_identity[key] for key in required_keys)


def _find_latest_matching_record(
    records_by_image_id: Dict[str, List[Dict[str, Any]]],
    current_identity: Dict[str, str],
) -> Dict[str, Any] | None:
    candidates = records_by_image_id.get(current_identity["image_id"], [])
    for record in reversed(candidates):
        if _identity_matches(record, current_identity):
            return record
    return None


def _summarize_cache_warnings(
    cache_records: List[Dict[str, Any]],
    current_signature: Dict[str, str],
    current_file_hashes: Dict[str, str],
) -> List[str]:
    warnings: List[str] = []
    signature_fields = [
        "dataset_name",
        "domain",
        "model_name",
        "prompt_hash",
        "generation_config_hash",
    ]

    for field in signature_fields:
        mismatch_count = sum(
            1
            for record in cache_records
            if str(record.get(field, "")).strip() and str(record.get(field)) != current_signature[field]
        )
        if mismatch_count:
            warnings.append(
                f"{field} changed for {mismatch_count} cached record(s): "
                f"current={current_signature[field]}"
            )

    file_hash_changed_ids = {
        image_id
        for image_id, current_hash in current_file_hashes.items()
        for record in cache_records
        if str(record.get("image_id", "")) == image_id
        and str(record.get("file_hash", "")).strip()
        and str(record.get("file_hash")) != current_hash
    }
    if file_hash_changed_ids:
        warnings.append(
            f"file_hash changed for {len(file_hash_changed_ids)} image(s) with the same image_id"
        )

    return warnings


def _generate_description_with_retry(
    chain,
    file_path: str,
    max_retries: int = 3,
    base_backoff_seconds: float = 2.0,
) -> tuple[str, str | None, int]:
    try:
        b64, mime_type = _prepare_image_payload(file_path)
    except Exception as e:
        error_message = str(e).strip() or repr(e)
        print(f"[WARN] Failed to prepare image payload for {file_path}: {error_message}")
        return "", error_message, 1

    last_error: str | None = None
    total_attempts = max_retries + 1
    for attempt in range(1, total_attempts + 1):
        try:
            desc = asyncio.run(chain.ainvoke({"image_b64": b64, "mime_type": mime_type}))
            if attempt > 1:
                print(f"[INFO] Retry succeeded for {file_path} on attempt {attempt}/{total_attempts}")
            return desc, None, attempt
        except Exception as e:
            error_message = str(e).strip() or repr(e)
            last_error = error_message
            print(
                f"[WARN] MLLM failed for {file_path} "
                f"(attempt {attempt}/{total_attempts}): {error_message}"
            )
            if _is_non_retryable_payload_error(error_message):
                print(f"[INFO] Stop retrying non-retryable 400 payload error for {file_path}")
                return "", error_message, attempt
            if attempt < total_attempts:
                sleep_seconds = base_backoff_seconds * (2 ** (attempt - 1))
                print(f"[INFO] Backing off for {sleep_seconds:.1f}s before retrying {file_path}")
                time.sleep(sleep_seconds)

    return "", last_error, total_attempts


def build_index(
    domain: str,
    image_records: List[dict],
    *,
    dataset_name: str = "UniDoc-Bench-subset",
    cache_dir: str | Path | None = None,
    resume: bool = True,
    retry_failed: bool = False,
    force_refresh: bool = False,
) -> None:
    """构建 MLLM 描述向量索引，支持本地缓存与断点续传。"""
    chain = get_image_description_chain()
    embedder = get_embedding_model()

    valid_records = [r for r in image_records if os.path.exists(r["file_path"])]
    skipped = len(image_records) - len(valid_records)
    if skipped:
        print(f"[SKIP] {skipped} images not found on disk.")
    if not valid_records:
        print("[WARNING] No valid images to process.")
        return

    cache_root = Path(cache_dir) if cache_dir else PROJECT_ROOT / "data" / "cache" / "unidoc_proposed"
    cache_file = _resolve_cache_file(cache_root, dataset_name, domain)

    chat_model = chain.chat_model
    current_signature = {
        "dataset_name": dataset_name,
        "domain": domain,
        "model_name": chat_model.model_name or "",
        "prompt_hash": _sha256_text(chain.prompt),
        "generation_config_hash": _stable_hash({
            "base_url": chat_model.base_url or "",
            "temperature": chat_model.temperature,
            "max_tokens": chat_model.max_tokens,
        }),
    }

    print(f"Using cache file: {cache_file}")
    print(
        "Run signature: "
        f"dataset={current_signature['dataset_name']}  "
        f"domain={current_signature['domain']}  "
        f"model={current_signature['model_name']}  "
        f"prompt_hash={current_signature['prompt_hash'][:12]}  "
        f"generation_config_hash={current_signature['generation_config_hash'][:12]}"
    )

    print(f"Computing file hashes for {len(valid_records)} images...")
    current_file_hashes = {
        str(record["id"]): _sha256_file(record["file_path"])
        for record in valid_records
    }

    cache_records = _load_cache_records(cache_file)
    records_by_image_id = _build_records_by_image_id(cache_records)
    cache_warnings = _summarize_cache_warnings(cache_records, current_signature, current_file_hashes)
    if cache_warnings:
        print(f"[WARN] Found {len(cache_warnings)} cache identity warning(s) in {cache_file}:")
        for message in cache_warnings:
            print(f"  - {message}")
        print("[WARN] Mismatched cached records will not be reused for this run.")

    ids: List[str] = []
    descriptions: List[str] = []
    metadatas: List[Dict[str, Any]] = []
    failed_files: List[tuple[str, str]] = []

    reused_success = 0
    skipped_cached_failures = 0
    regenerated_success = 0
    regenerated_failures = 0

    print(f"Processing {len(valid_records)} images for UniDoc proposed index...")
    for i, record in enumerate(valid_records, start=1):
        image_id = str(record["id"])
        file_path = record["file_path"]
        current_identity = {
            **current_signature,
            "image_id": image_id,
            "file_hash": current_file_hashes[image_id],
        }
        cached_record = _find_latest_matching_record(records_by_image_id, current_identity)

        if not force_refresh and resume and cached_record and cached_record.get("status") == "success":
            description = str(cached_record.get("description", ""))
            ids.append(image_id)
            descriptions.append(description)
            metadatas.append({
                "file_path": file_path,
                "domain": domain,
                "source": "unidoc_proposed",
                "dataset_name": dataset_name,
            })
            reused_success += 1
        elif (
            not force_refresh
            and resume
            and not retry_failed
            and cached_record
            and cached_record.get("status") == "failed"
        ):
            skipped_cached_failures += 1
            error_message = str(cached_record.get("error", "unknown error"))
            failed_files.append((file_path, f"cached failure not retried: {error_message}"))
            print(f"[SKIP] Cached failure for {image_id}; use --retry-failed to regenerate.")
        else:
            desc, error_message, attempt_count = _generate_description_with_retry(chain, file_path)
            cache_record = {
                **current_identity,
                "file_path": file_path,
                "description": desc,
                "status": "success" if error_message is None else "failed",
                "error": error_message,
                "attempt_count": attempt_count,
                "updated_at": _utc_now_iso(),
            }
            _append_cache_record(cache_file, cache_record)
            records_by_image_id.setdefault(image_id, []).append(cache_record)

            if error_message is None:
                ids.append(image_id)
                descriptions.append(desc)
                metadatas.append({
                    "file_path": file_path,
                    "domain": domain,
                    "source": "unidoc_proposed",
                    "dataset_name": dataset_name,
                })
                regenerated_success += 1
            else:
                regenerated_failures += 1
                failed_files.append((file_path, error_message))

        if i % 10 == 0 or i == len(valid_records):
            print(
                f"  {i}/{len(valid_records)} done | "
                f"reused={reused_success} regenerated={regenerated_success} "
                f"failed={len(failed_files)}"
            )
            if i < len(valid_records):
                time.sleep(2)

    print(
        "Description processing summary: "
        f"reused_success={reused_success}, "
        f"regenerated_success={regenerated_success}, "
        f"regenerated_failures={regenerated_failures}, "
        f"skipped_cached_failures={skipped_cached_failures}"
    )
    if failed_files:
        print("Failed or skipped files:")
        for file_path, error_message in failed_files:
            print(f"  - {file_path}: {error_message}")

    if not ids:
        print("[ERROR] No successful descriptions available for embedding. Index was not rebuilt.")
        return

    print(f"Embedding {len(descriptions)} descriptions...")
    embeddings = embedder.embed_documents(descriptions)

    col_name = _collection_name(domain)
    try:
        _client.delete_collection(col_name)
    except Exception:
        pass
    col = _client.get_or_create_collection(name=col_name)
    col.add(embeddings=embeddings, documents=descriptions, ids=ids, metadatas=metadatas)
    print(f"Index built: {len(ids)} images in '{col_name}'")


def retrieve(query: str, domain: str, top_k: int = 10) -> List[str]:
    embedder = get_embedding_model()
    emb = embedder.embed_query(query)
    col = _client.get_or_create_collection(name=_collection_name(domain))
    results = col.query(query_embeddings=[emb], n_results=top_k)
    return [str(i) for i in results.get("ids", [[]])[0]]


def check_index(domain: str) -> bool:
    col = _client.get_or_create_collection(name=_collection_name(domain))
    return col.count() > 0
