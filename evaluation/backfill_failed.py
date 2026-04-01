"""
补全脚本：对 unidoc_gen_batch 结果中缺失 / [ERROR] 的条目，
使用实时 API 逐条重新推理并回填。

用法（从项目根目录）：
  python -m evaluation.backfill_failed
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set

# ── 加载 backend/.env ──────────────────────────────────────────────
_env_path = Path(__file__).parent.parent / "backend" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from evaluation.datasets.unidoc_subset import DOMAINS, UniDocQuerySample, load_unidoc_domain  # noqa: E402
from evaluation.methods import unidoc_clip, unidoc_ocr, unidoc_proposed  # noqa: E402
from evaluation._generation_core import read_image_as_base64, generate_with_images  # noqa: E402

CROSSDOMAIN_KEY = "crossdomain"
BATCH_DIR = Path(__file__).parent.parent / "data" / "rag_outputs" / "unidoc_gen_batch"
SUBSET_ROOT = Path(__file__).parent.parent / "data" / "UniDoc-Bench-subset"

METHODS = ["proposed", "baseline_clip", "baseline_ocr", "no_rag"]


def _utf8_stdio():
    for s in ("stdout", "stderr"):
        obj = getattr(sys, s, None)
        fn = getattr(obj, "reconfigure", None)
        if callable(fn):
            fn(encoding="utf-8", errors="replace")


_utf8_stdio()


# ── 辅助：与 run_unidoc_gen_batch.py 一致的 qid 生成 ──────────────
def _qid(query: str, domain: str) -> str:
    return hashlib.md5(f"{query}||{domain}".encode()).hexdigest()[:16]


# ── 辅助：从 ChromaDB 查 file_path ────────────────────────────────
def _ids_to_file_paths(ids: List[str]) -> List[str]:
    import chromadb
    from chromadb.config import Settings as CS
    from app.core.config import settings as cfg
    client = chromadb.Client(CS(is_persistent=True, persist_directory=cfg.CHROMA_PERSIST_DIR))
    id2p: Dict[str, str] = {}
    for col in [
        f"unidoc_{CROSSDOMAIN_KEY}_proposed",
        f"unidoc_{CROSSDOMAIN_KEY}_clip",
        f"unidoc_{CROSSDOMAIN_KEY}_ocr",
    ]:
        if len(id2p) == len(ids):
            break
        try:
            c = client.get_collection(col)
            rem = [i for i in ids if i not in id2p]
            r = c.get(ids=rem, include=["metadatas"])
            for img_id, meta in zip(r["ids"], r["metadatas"]):
                if img_id not in id2p and meta and meta.get("file_path"):
                    id2p[img_id] = meta["file_path"]
        except Exception:
            continue
    root = SUBSET_ROOT
    for img_id in ids:
        if img_id not in id2p and (root / img_id).exists():
            id2p[img_id] = str(root / img_id)
    return [id2p.get(i, "") for i in ids]


def _ids_to_ocr_texts(ids: List[str]) -> List[str]:
    import chromadb
    from chromadb.config import Settings as CS
    from app.core.config import settings as cfg
    client = chromadb.Client(CS(is_persistent=True, persist_directory=cfg.CHROMA_PERSIST_DIR))
    id2t: Dict[str, str] = {}
    try:
        c = client.get_collection(f"unidoc_{CROSSDOMAIN_KEY}_ocr")
        r = c.get(ids=ids, include=["metadatas"])
        for img_id, meta in zip(r["ids"], r["metadatas"]):
            if meta and meta.get("ocr_text"):
                id2t[img_id] = meta["ocr_text"]
    except Exception:
        pass
    return [id2t.get(i, "") for i in ids]


# ── 核心：单条实时推理（复用 run_unidoc_gen.py 逻辑）──────────────
async def _generate_no_rag(query: str) -> str:
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


async def run_one(sample: UniDocQuerySample, method: str, top_k: int = 5) -> Dict[str, Any]:
    qid = _qid(sample.query, sample.domain)

    if method == "no_rag":
        answer = await _generate_no_rag(sample.query)
        return {
            "query_id": qid,
            "query": sample.query,
            "domain": sample.domain,
            "question_type": sample.question_type,
            "answer_type": sample.answer_type,
            "reference_answer": sample.answer,
            "generated_answer": answer,
            "retrieved_ids": [],
            "method": method,
        }

    # 检索
    if method == "proposed":
        ids = unidoc_proposed.retrieve(sample.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
    elif method == "baseline_clip":
        ids = unidoc_clip.retrieve(sample.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
    elif method == "baseline_ocr":
        ids = unidoc_ocr.retrieve(sample.query, domain=CROSSDOMAIN_KEY, top_k=top_k)
    else:
        raise ValueError(f"Unknown method: {method}")

    # baseline_ocr 走纯文本 prompt
    if method == "baseline_ocr":
        ocr_texts = _ids_to_ocr_texts(ids)
        combined = "\n\n".join(f"[片段{i+1}] {t if t else '[no text]'}" for i, t in enumerate(ocr_texts))
        from app.langchain_integration.models import get_chat_model
        from langchain_core.messages import HumanMessage
        ocr_prompt = (
            f"你是一个知识库问答助手。以下是从知识库中检索到的相关文字内容：\n\n"
            f"{combined}\n\n用户问题：{sample.query}\n\n请基于上述内容回答问题。"
        )
        model = get_chat_model()
        try:
            result = await model._agenerate([HumanMessage(content=ocr_prompt)])
            answer = result.generations[0].message.content
        except Exception as e:
            answer = f"[ERROR] {type(e).__name__}: {e}"
    else:
        # proposed / baseline_clip 走图片
        file_paths = _ids_to_file_paths(ids)
        image_payloads = [p for fp in file_paths if (p := read_image_as_base64(fp))]
        try:
            answer = await generate_with_images(sample.query, image_payloads)
        except Exception as e:
            answer = f"[ERROR] {type(e).__name__}: {e}"

    return {
        "query_id": qid,
        "query": sample.query,
        "domain": sample.domain,
        "question_type": sample.question_type,
        "answer_type": sample.answer_type,
        "reference_answer": sample.answer,
        "generated_answer": answer,
        "retrieved_ids": ids,
        "method": method,
    }


# ── 主流程 ─────────────────────────────────────────────────────────
def main():
    # 1) 加载全量样本，建 qid -> sample 映射
    all_samples: List[UniDocQuerySample] = []
    for domain in DOMAINS:
        try:
            ds = load_unidoc_domain(domain, SUBSET_ROOT)
            all_samples.extend(ds)
        except FileNotFoundError as e:
            print(f"[SKIP] {e}")
    print(f"Loaded {len(all_samples)} total samples")

    qid_to_sample: Dict[str, UniDocQuerySample] = {}
    for s in all_samples:
        qid_to_sample[_qid(s.query, s.domain)] = s

    all_qids = set(qid_to_sample.keys())
    print(f"Unique query_ids: {len(all_qids)}")

    # 2) 逐方法处理
    for method in METHODS:
        result_file = BATCH_DIR / f"{method}_results.json"
        if not result_file.exists():
            print(f"\n[SKIP] {result_file} not found")
            continue

        records: List[Dict[str, Any]] = json.loads(result_file.read_text(encoding="utf-8"))
        before_count = len(records)

        # 已有 qid 集合
        existing_qids: Set[str] = {r["query_id"] for r in records}
        # 找 [ERROR] 条目的 qid
        error_qids: Set[str] = {
            r["query_id"] for r in records
            if str(r.get("generated_answer", "")).strip().startswith("[ERROR]")
        }
        # 缺失的 qid
        missing_qids = all_qids - existing_qids

        to_backfill = missing_qids | error_qids
        if not to_backfill:
            print(f"\n=== {method}: 无需补全（{before_count} 条全部正常）===")
            continue

        print(f"\n=== {method}: 需补全 {len(to_backfill)} 条 "
              f"（缺失 {len(missing_qids)}, ERROR {len(error_qids)}）===")

        # 建 qid -> record index 映射（用于替换 ERROR 条目）
        qid_to_idx: Dict[str, int] = {}
        for idx, r in enumerate(records):
            qid_to_idx[r["query_id"]] = idx

        success = 0
        still_fail = 0
        for i, qid in enumerate(sorted(to_backfill), 1):
            sample = qid_to_sample.get(qid)
            if sample is None:
                print(f"  [{i}/{len(to_backfill)}] qid={qid} 在数据集中找不到，跳过")
                continue

            print(f"  [{i}/{len(to_backfill)}] qid={qid} domain={sample.domain} "
                  f"query={sample.query[:50]}...")

            try:
                new_record = asyncio.run(run_one(sample, method))
            except Exception as e:
                print(f"    FAIL: {e}")
                still_fail += 1
                time.sleep(2)
                continue

            ans = str(new_record.get("generated_answer", ""))
            if ans.startswith("[ERROR]"):
                print(f"    仍然失败: {ans[:80]}")
                still_fail += 1
            else:
                success += 1
                print(f"    OK ({len(ans)} chars)")

            # 回填
            if qid in qid_to_idx:
                # 替换原有 ERROR 条目
                records[qid_to_idx[qid]] = new_record
            else:
                # 新增缺失条目
                records.append(new_record)
                qid_to_idx[qid] = len(records) - 1

            # 每条都写一次，防止中断丢失
            result_file.write_text(
                json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            time.sleep(1)  # 控制 API 速率

        after_count = len(records)
        after_errors = sum(
            1 for r in records
            if str(r.get("generated_answer", "")).strip().startswith("[ERROR]")
        )
        print(f"  补全完成: before={before_count} after={after_count} "
              f"success={success} still_fail={still_fail} remaining_errors={after_errors}")

    # 3) 最终统计
    print("\n" + "=" * 60)
    print("补全后最终统计")
    print("=" * 60)
    for method in METHODS:
        result_file = BATCH_DIR / f"{method}_results.json"
        if not result_file.exists():
            continue
        records = json.loads(result_file.read_text(encoding="utf-8"))
        total = len(records)
        errors = sum(1 for r in records if str(r.get("generated_answer", "")).strip().startswith("[ERROR]"))
        print(f"  {method:20s}  total={total:4d}  errors={errors:4d}  success={total - errors:4d}")


if __name__ == "__main__":
    main()
