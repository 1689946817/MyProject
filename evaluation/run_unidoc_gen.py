"""
生成器评估 — UniDoc-Bench-subset 数据集。

使用跨领域混合候选池（crossdomain）中已建好的向量索引检索 top-k 图片，
将检索到的所有图片传给 MLLM 生成答案，并与 ground-truth answer 一同保存。

支持的方法：
  proposed        图片语义描述检索 → 传原始图片给 MLLM
  baseline_clip   多模态 embedding 检索 → 传原始图片给 MLLM
  baseline_ocr    OCR 文字检索 → 传原始图片给 MLLM
  no_rag          不检索，直接问 MLLM

使用示例（从项目根目录）：
  python -m evaluation.run_unidoc_gen \\
    --method proposed \\
    --top-k 5 \\
    --output-dir data/rag_outputs/unidoc_gen
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 加载 backend/.env
_env_path = Path(__file__).parent.parent / "backend" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from evaluation._generation_core import (  # noqa: E402
    read_image_as_base64,
    generate_with_images,
)
from evaluation.datasets.unidoc_subset import (  # noqa: E402
    DOMAINS,
    UniDocQuerySample,
    load_unidoc_domain,
)
from evaluation.methods import unidoc_clip, unidoc_ocr, unidoc_proposed  # noqa: E402

CROSSDOMAIN_KEY = "crossdomain"


def _configure_utf8_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


_configure_utf8_stdio()


def _ids_to_file_paths_unidoc(ids: List[str], domain: str) -> List[str]:
    """从 UniDoc ChromaDB 集合中查询 file_path。"""
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from app.core.config import settings as app_settings

    client = chromadb.Client(
        ChromaSettings(is_persistent=True, persist_directory=app_settings.CHROMA_PERSIST_DIR)
    )
    id_to_path: Dict[str, str] = {}
    candidate_collections = [
        f"unidoc_{domain}_proposed",
        f"unidoc_{domain}_clip",
        f"unidoc_{domain}_ocr",
    ]
    for col_name in candidate_collections:
        if len(id_to_path) == len(ids):
            break
        try:
            col = client.get_collection(col_name)
            remaining = [i for i in ids if i not in id_to_path]
            result = col.get(ids=remaining, include=["metadatas"])
            for img_id, meta in zip(result["ids"], result["metadatas"]):
                if img_id not in id_to_path and meta and meta.get("file_path"):
                    id_to_path[img_id] = meta["file_path"]
        except Exception:
            continue
    # 对仍未找到 file_path 的 id，尝试从 subset_root 直接构建路径
    subset_root = Path(__file__).parent.parent / "data" / "UniDoc-Bench-subset"
    for img_id in ids:
        if img_id not in id_to_path:
            candidate = subset_root / img_id
            if candidate.exists():
                id_to_path[img_id] = str(candidate)
    return [id_to_path.get(i, "") for i in ids]


async def _generate_no_rag(query: str) -> str:
    """不检索，直接问 MLLM。"""
    from app.langchain_integration.models import get_chat_model
    from langchain_core.messages import HumanMessage

    prompt = (
        "你是一个问答助手，请直接回答下面的问题。\n\n"
        f"问题：{query}\n\n"
        "如果不确定请明确说明。"
    )
    model = get_chat_model()
    result = await model._agenerate([HumanMessage(content=prompt)])
    return result.generations[0].message.content


async def _run_one_sample(
    sample: UniDocQuerySample,
    method: str,
    top_k: int,
) -> Dict[str, Any]:
    _qid = hashlib.md5(f"{sample.query}||{sample.domain}".encode()).hexdigest()[:16]

    if method == "no_rag":
        answer = await _generate_no_rag(sample.query)
        return {
            "query_id": _qid,
            "query": sample.query,
            "domain": sample.domain,
            "question_type": sample.question_type,
            "answer_type": sample.answer_type,
            "reference_answer": sample.answer,
            "generated_answer": answer,
            "retrieved_ids": [],
            "method": method,
        }

    if method == "proposed":
        ids = unidoc_proposed.retrieve(sample.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
    elif method == "baseline_clip":
        ids = unidoc_clip.retrieve(sample.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
    elif method == "baseline_ocr":
        ids = unidoc_ocr.retrieve(sample.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
    else:
        raise ValueError(f"Unsupported method: {method}")

    file_paths = _ids_to_file_paths_unidoc(ids, domain=CROSSDOMAIN_KEY)
    image_payloads = [payload for p in file_paths if (payload := read_image_as_base64(p))]

    try:
        answer = await generate_with_images(sample.query, image_payloads)
    except Exception as e:
        import traceback
        print(f"  [WARN] 生成失败: {type(e).__name__}: {e}")
        print(traceback.format_exc())
        answer = f"[ERROR] {type(e).__name__}: {e}"

    return {
        "query_id": _qid,
        "query": sample.query,
        "domain": sample.domain,
        "question_type": sample.question_type,
        "answer_type": sample.answer_type,
        "reference_answer": sample.answer,
        "generated_answer": answer,
        "retrieved_ids": ids,
        "method": method,
    }


def _load_existing(output_path: Path) -> List[Dict[str, Any]]:
    if not output_path.exists():
        return []
    try:
        return json.loads(output_path.read_text(encoding="utf-8"))
    except Exception:
        return []


async def run_generation(
    samples: List[UniDocQuerySample],
    method: str,
    top_k: int,
    output_path: Path,
) -> None:
    existing = _load_existing(output_path)
    # 用 (query, domain) 作为去重键
    done_keys = {(r["query"], r["domain"]) for r in existing}
    records = list(existing)

    total = len(samples)
    skipped = 0
    for i, sample in enumerate(samples, start=1):
        key = (sample.query, sample.domain)
        if key in done_keys:
            skipped += 1
            continue
        print(f"[{i}/{total}] method={method} domain={sample.domain} query={sample.query[:60]}")
        record = await _run_one_sample(sample, method, top_k)
        records.append(record)
        done_keys.add(key)
        output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Done. {len(records)} records saved to {output_path} (skipped {skipped} cached).")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成器评估 — UniDoc-Bench-subset")
    parser.add_argument(
        "--method",
        type=str,
        choices=["proposed", "baseline_clip", "baseline_ocr", "no_rag"],
        required=True,
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output-dir", type=str, default="data/rag_outputs/unidoc_gen")
    parser.add_argument(
        "--subset-root",
        type=str,
        default="data/UniDoc-Bench-subset",
        help="UniDoc-Bench-subset 根目录",
    )
    parser.add_argument(
        "--domains",
        type=str,
        nargs="+",
        default=None,
        help="指定评测的领域（默认全部 8 个）",
    )
    args = parser.parse_args()

    subset_root = Path(args.subset_root)
    domains = args.domains or DOMAINS

    samples: List[UniDocQuerySample] = []
    for domain in domains:
        try:
            domain_samples = load_unidoc_domain(domain, subset_root)
            samples.extend(domain_samples)
            print(f"Loaded {len(domain_samples)} samples from domain '{domain}'")
        except FileNotFoundError as e:
            print(f"[SKIP] {e}")

    if not samples:
        print("No samples loaded. Check --subset-root.")
        return

    if args.method == "baseline_ocr" and not unidoc_ocr.check_index(CROSSDOMAIN_KEY):
        print(
            "[ERROR] OCR index for crossdomain is missing or unhealthy. "
            "Rebuild it with `python -m evaluation.run_unidoc_full_eval --method baseline_ocr --build-index` first."
        )
        return

    print(f"Total samples: {len(samples)}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"unidoc_gen_{args.method}_top{args.top_k}.json"

    asyncio.run(run_generation(samples, args.method, args.top_k, output_path))


if __name__ == "__main__":
    main()
