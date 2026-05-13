"""
UniDoc-Bench Proposed 方法：MLLM 描述 + 文本向量检索。

核心流程：
  1. 对每张图像调用 MLLM 生成结构化文本描述
  2. 将描述文本通过 Embedding 模型向量化
  3. 存入 ChromaDB 集合（命名规则：unidoc_{domain}_proposed）
  4. 检索时将查询文本 Embedding，在向量库中执行余弦相似度检索

缓存策略：
  - 描述结果以 JSONL 格式持久化到本地文件（data/cache/unidoc_proposed/）
  - 缓存记录包含完整的身份签名（model_name、prompt_hash、generation_config_hash、file_hash）
  - 签名不匹配的缓存不会被复用，确保模型/Prompt 变更后自动重新生成
  - 支持跨数据集缓存复用（reuse_cache_dataset_names），同一图片无需重复生成描述

断点续传：
  - 每条描述生成后立即追加到 JSONL 文件并 fsync，进程中断不丢失已完成的记录
  - resume=True 时跳过已有成功缓存的图片
  - retry_failed=True 时重试之前失败的记录

图片压缩：
  - 当图片 base64 编码超过 9.5MB 时，自动进行尺寸/质量压缩
  - 压缩梯度：max_side=[1800, 1600, 1280] × quality=[85, 75, 65]
  - 超过最小压缩仍超限时抛出 ValueError
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

# 项目根目录（evaluation/ 的上两级）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.langchain_integration.chains import get_image_description_chain  # noqa: E402
from app.langchain_integration.models import get_embedding_model, guess_image_mime_type  # noqa: E402

# 初始化持久化 ChromaDB 客户端，使用后端配置的存储目录
_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)


def _collection_name(domain: str) -> str:
    """生成 ChromaDB 集合名称，命名规则：unidoc_{domain}_proposed。

    Args:
        domain: 领域名称（如 finance、healthcare 等）。

    Returns:
        str: 集合名称。
    """
    return f"unidoc_{domain}_proposed"


def _sha256_text(text: str) -> str:
    """计算文本的 SHA-256 哈希值，用于 prompt_hash 和缓存签名。

    Args:
        text: 待哈希的文本字符串。

    Returns:
        str: 64 位十六进制哈希字符串。
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(file_path: str) -> str:
    """计算文件的 SHA-256 哈希值，用于检测文件内容是否变更。

    分块读取文件（每块 1MB），避免大文件一次性加载到内存。

    Args:
        file_path: 文件路径。

    Returns:
        str: 64 位十六进制哈希字符串。
    """
    digest = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_hash(payload: Dict[str, Any]) -> str:
    """对字典进行确定性序列化后计算 SHA-256，用于 generation_config_hash。

    使用 sort_keys=True 确保相同内容的字典总是产生相同的哈希值。

    Args:
        payload: 待哈希的字典（如生成配置参数）。

    Returns:
        str: 64 位十六进制哈希字符串。
    """
    return _sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _utc_now_iso() -> str:
    """获取当前 UTC 时间的 ISO 8601 字符串（不含微秒），用于缓存记录时间戳。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resolve_cache_file(cache_dir: str | Path, dataset_name: str, domain: str) -> Path:
    """解析缓存文件路径，结构：cache_dir / dataset_name / domain / descriptions.jsonl。

    Args:
        cache_dir: 缓存根目录。
        dataset_name: 数据集名称（如 UniDoc-Bench-subset）。
        domain: 领域名称。

    Returns:
        Path: 缓存文件的完整路径。
    """
    return Path(cache_dir) / dataset_name / domain / "descriptions.jsonl"


def _estimate_base64_size(raw_size: int) -> int:
    """估算原始二进制数据 base64 编码后的字节数。

    base64 编码将每 3 字节扩展为 4 字符，向上取整。

    Args:
        raw_size: 原始二进制数据字节数。

    Returns:
        int: base64 编码后的近似字节数。
    """
    return ((raw_size + 2) // 3) * 4


def _prepare_image_payload(
    file_path: str,
    *,
    max_base64_bytes: int = 9_500_000,
) -> tuple[str, str]:
    """准备 MLLM 请求的图片 payload（base64 编码 + MIME 类型）。

    如果图片 base64 编码超过 max_base64_bytes 限制，
    自动进行多级压缩（尺寸×质量组合），直到满足大小要求。

    压缩梯度：
    - max_side: 1800 → 1600 → 1280（长边像素）
    - quality: 85 → 75 → 65（JPEG 质量）

    Args:
        file_path: 图片文件路径。
        max_base64_bytes: base64 编码后的最大字节数，默认 9.5MB。

    Returns:
        tuple[str, str]: (base64 编码字符串, MIME 类型)。
            原始图片未压缩时 MIME 类型由文件后缀决定；
            压缩后统一为 "image/jpeg"。

    Raises:
        ValueError: 图片即使经过最小压缩仍超过大小限制。
    """
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
    """判断错误消息是否属于不可重试的 payload 错误（HTTP 400）。

    当错误是 400 Bad Request 且涉及 payload/base64/image/size 等关键词时，
    说明请求体本身有问题（如图片太大、格式不支持），重试无法解决。

    Args:
        error_message: 异常消息字符串。

    Returns:
        bool: True 表示不可重试，应立即停止对该图片的尝试。
    """
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
    """从 JSONL 缓存文件加载所有记录。

    JSONL 格式：每行一个 JSON 对象，空行和格式错误的行会被跳过。

    Args:
        cache_file: 缓存文件路径（descriptions.jsonl）。

    Returns:
        List[Dict[str, Any]]: 所有有效记录的列表。
    """
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
    """将单条记录追加到 JSONL 缓存文件，并立即 fsync 确保持久化。

    追加模式（而非覆盖写入）确保断点续传：
    - 每条描述生成后立即写入磁盘
    - 调用 os.fsync 强制刷盘，避免进程崩溃时数据丢失
    - 父目录不存在时自动创建

    Args:
        cache_file: 缓存文件路径。
        record: 待追加的记录字典。
    """
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with cache_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _clone_record_for_dataset(cache_record: Dict[str, Any], *, dataset_name: str, file_path: str) -> Dict[str, Any]:
    """克隆缓存记录并更新数据集信息，用于跨数据集缓存复用。

    当 reuse_cache_dataset_names 中的历史缓存记录被复用到当前数据集时，
    需要更新 dataset_name、file_path 和 updated_at 字段。

    Args:
        cache_record: 原始缓存记录。
        dataset_name: 当前数据集名称。
        file_path: 当前数据集中的文件路径。

    Returns:
        Dict[str, Any]: 更新后的记录副本。
    """
    cloned = dict(cache_record)
    cloned["dataset_name"] = dataset_name
    cloned["file_path"] = file_path
    cloned["updated_at"] = _utc_now_iso()
    return cloned


def _build_records_by_image_id(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """将缓存记录列表按 image_id 分组，构建索引字典。

    同一 image_id 可能有多条记录（重试、不同配置等），
    保留所有记录并按时间顺序排列，查找时从后往前取最新。

    Args:
        records: 缓存记录列表。

    Returns:
        Dict[str, List[Dict[str, Any]]]: {image_id: [记录列表]} 的分组字典。
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        image_id = str(record.get("image_id", "")).strip()
        if not image_id:
            continue
        grouped.setdefault(image_id, []).append(record)
    return grouped


def _identity_matches(
    cache_record: Dict[str, Any],
    current_identity: Dict[str, str],
    *,
    allow_dataset_name_mismatch: bool = False,
    allow_domain_mismatch: bool = False,
) -> bool:
    """检查缓存记录的身份签名是否与当前运行配置匹配。

    身份签名包含 6 个字段：
    - dataset_name: 数据集名称
    - domain: 领域名称
    - image_id: 图像 ID
    - file_hash: 图像文件的 SHA-256 哈希（检测文件内容变更）
    - model_name: MLLM 模型名称
    - prompt_hash: Prompt 的 SHA-256 哈希（检测 Prompt 变更）
    - generation_config_hash: 生成参数的哈希（检测温度、max_tokens 等变更）

    跨数据集复用时可允许 dataset_name 和 domain 不匹配。

    Args:
        cache_record: 缓存记录。
        current_identity: 当前运行的身份签名。
        allow_dataset_name_mismatch: 是否允许 dataset_name 不匹配。
        allow_domain_mismatch: 是否允许 domain 不匹配。

    Returns:
        bool: True 表示身份匹配，可以复用该缓存。
    """
    required_keys = [
        "domain",
        "image_id",
        "file_hash",
        "model_name",
        "prompt_hash",
        "generation_config_hash",
    ]
    if not allow_dataset_name_mismatch:
        required_keys = ["dataset_name", *required_keys]
    if allow_domain_mismatch:
        required_keys = [k for k in required_keys if k != "domain"]
    return all(str(cache_record.get(key, "")) == current_identity[key] for key in required_keys)


def _find_latest_matching_record(
    records_by_image_id: Dict[str, List[Dict[str, Any]]],
    current_identity: Dict[str, str],
    *,
    allow_dataset_name_mismatch: bool = False,
    allow_domain_mismatch: bool = False,
) -> Dict[str, Any] | None:
    """查找与当前身份签名匹配的最新缓存记录。

    从 image_id 对应的记录列表中从后往前搜索（最新记录优先），
    返回第一个身份签名完全匹配的记录。

    Args:
        records_by_image_id: 按 image_id 分组的缓存记录索引。
        current_identity: 当前运行的身份签名。
        allow_dataset_name_mismatch: 是否允许跨数据集复用。
        allow_domain_mismatch: 是否允许跨领域复用。

    Returns:
        Dict[str, Any] | None: 匹配的缓存记录，未找到返回 None。
    """
    candidates = records_by_image_id.get(current_identity["image_id"], [])
    for record in reversed(candidates):
        if _identity_matches(
            record,
            current_identity,
            allow_dataset_name_mismatch=allow_dataset_name_mismatch,
            allow_domain_mismatch=allow_domain_mismatch,
        ):
            return record
    return None


def _summarize_cache_warnings(
    cache_records: List[Dict[str, Any]],
    current_signature: Dict[str, str],
    current_file_hashes: Dict[str, str],
) -> List[str]:
    """生成缓存签名变更的警告信息列表。

    检查以下变更情况：
    1. dataset_name / domain / model_name / prompt_hash / generation_config_hash 变更
    2. 同 image_id 的文件内容变更（file_hash 不同）

    警告仅用于提示用户，不阻止流程继续执行（不匹配的缓存不会被复用）。

    Args:
        cache_records: 已加载的缓存记录列表。
        current_signature: 当前运行的签名字段。
        current_file_hashes: {image_id: file_sha256} 的当前文件哈希映射。

    Returns:
        List[str]: 警告消息列表。
    """
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
    """调用 MLLM 生成图像描述，支持自动重试和指数退避。

    重试策略：
    - 最多重试 max_retries 次（共 max_retries+1 次尝试）
    - 退避时间 = base_backoff_seconds * 2^(attempt-1)，呈指数增长
    - 遇到 400 payload 错误（图片太大等）立即停止，不重试

    Args:
        chain: ImageDescriptionChain 实例。
        file_path: 图像文件路径。
        max_retries: 最大重试次数，默认 3。
        base_backoff_seconds: 退避基准秒数，默认 2.0。

    Returns:
        tuple[str, str | None, int]:
            - 描述文本（失败时为空字符串）
            - 错误消息（成功时为 None）
            - 实际尝试次数
    """
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
    reuse_cache_dataset_names: List[str] | None = None,
) -> None:
    """构建 MLLM 描述向量索引，支持本地缓存与断点续传。

    完整流程：
    1. 验证图片文件是否存在，跳过缺失文件
    2. 计算当前运行的身份签名（模型、Prompt、生成参数、文件哈希）
    3. 加载本地缓存，检查签名匹配性
    4. 对每张图片：命中缓存则复用，否则调用 MLLM 生成描述
    5. 将成功生成的描述向量化，存入 ChromaDB 集合

    Args:
        domain: 领域名称，影响集合命名 unidoc_{domain}_proposed。
        image_records: 图像记录列表，每条需包含 id 和 file_path。
        dataset_name: 数据集名称，影响缓存目录和集合元数据。
        cache_dir: 缓存根目录，默认 data/cache/unidoc_proposed/。
        resume: 是否启用断点续传（跳过已有成功缓存）。
        retry_failed: 是否重试之前失败的记录。
        force_refresh: 是否强制重新生成所有描述（忽略缓存）。
        reuse_cache_dataset_names: 可复用的历史数据集缓存名称列表。
    """
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
    reuse_cache_dataset_names = reuse_cache_dataset_names or []
    reuse_cache_dataset_names = [name for name in reuse_cache_dataset_names if name and name != dataset_name]
    reuse_cache_files = []
    for reuse_dataset_name in reuse_cache_dataset_names:
        reuse_dataset_root = cache_root / reuse_dataset_name
        if reuse_dataset_root.exists():
            # 枚举该 dataset 下所有领域子目录，避免 domain key 不匹配
            domain_dirs = [d for d in reuse_dataset_root.iterdir() if d.is_dir()]
            for domain_dir in domain_dirs:
                candidate = domain_dir / "descriptions.jsonl"
                if candidate.exists():
                    reuse_cache_files.append(candidate)
        else:
            reuse_cache_files.append(_resolve_cache_file(cache_root, reuse_dataset_name, domain))

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
    if reuse_cache_files:
        print("Reusing historical cache files:")
        for reuse_cache_file in reuse_cache_files:
            print(f"  - {reuse_cache_file}")
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

    historical_records_by_image_id_list: List[Dict[str, List[Dict[str, Any]]]] = []
    for reuse_cache_file in reuse_cache_files:
        historical_cache_records = _load_cache_records(reuse_cache_file)
        historical_cache_warnings = _summarize_cache_warnings(
            historical_cache_records,
            {**current_signature, "dataset_name": Path(reuse_cache_file).parent.parent.name},
            current_file_hashes,
        )
        if historical_cache_warnings:
            print(f"[WARN] Found {len(historical_cache_warnings)} cache identity warning(s) in {reuse_cache_file}:")
            for message in historical_cache_warnings:
                print(f"  - {message}")
            print("[WARN] Only records matching current image/model/prompt signature will be reused.")
        historical_records_by_image_id_list.append(_build_records_by_image_id(historical_cache_records))

    ids: List[str] = []
    descriptions: List[str] = []
    metadatas: List[Dict[str, Any]] = []
    failed_files: List[tuple[str, str]] = []

    reused_success = 0
    reused_historical_success = 0
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
        historical_cached_record = None
        if not force_refresh and resume and cached_record is None:
            for historical_records_by_image_id in historical_records_by_image_id_list:
                historical_cached_record = _find_latest_matching_record(
                    historical_records_by_image_id,
                    current_identity,
                    allow_dataset_name_mismatch=True,
                    allow_domain_mismatch=True,
                )
                if historical_cached_record is not None:
                    break

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
        elif not force_refresh and resume and historical_cached_record and historical_cached_record.get("status") == "success":
            description = str(historical_cached_record.get("description", ""))
            promoted_record = _clone_record_for_dataset(
                historical_cached_record,
                dataset_name=dataset_name,
                file_path=file_path,
            )
            _append_cache_record(cache_file, promoted_record)
            records_by_image_id.setdefault(image_id, []).append(promoted_record)
            ids.append(image_id)
            descriptions.append(description)
            metadatas.append({
                "file_path": file_path,
                "domain": domain,
                "source": "unidoc_proposed",
                "dataset_name": dataset_name,
            })
            reused_historical_success += 1
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
                f"reused_current={reused_success} reused_history={reused_historical_success} "
                f"regenerated={regenerated_success} failed={len(failed_files)}"
            )
            if i < len(valid_records):
                time.sleep(2)

    print(
        "Description processing summary: "
        f"reused_success={reused_success}, "
        f"reused_historical_success={reused_historical_success}, "
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
    """使用 Proposed 方法检索图像。

    检索路径：查询文本 → Embedding 模型编码 → ChromaDB 余弦相似度检索。

    Args:
        query: 查询文本。
        domain: 领域名称，决定检索哪个集合。
        top_k: 返回的检索结果数量，默认 10。

    Returns:
        List[str]: top_k 个预测图像 ID 列表，按相似度降序排列。
    """
    embedder = get_embedding_model()
    emb = embedder.embed_query(query)
    col = _client.get_or_create_collection(name=_collection_name(domain))
    results = col.query(query_embeddings=[emb], n_results=top_k)
    return [str(i) for i in results.get("ids", [[]])[0]]


def check_index(domain: str) -> bool:
    """检查指定领域的 Proposed 索引是否已构建且非空。

    Args:
        domain: 领域名称。

    Returns:
        bool: True 表示索引包含至少一条记录。
    """
    col = _client.get_or_create_collection(name=_collection_name(domain))
    return col.count() > 0
