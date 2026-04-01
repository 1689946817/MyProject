"""
UniDoc 生成器多维度评分脚本 - 复用 evaluators_openai 六大评估器。

评估维度（与 evaluators_openai.py 一致）：
  1. answer_correctness      - 答案正确性       (0/1)
  2. answer_relevancy        - 答案相关性       (0/1)
  3. text_context_relevancy  - 文本上下文相关性  (0/1)
  4. image_context_relevancy - 图像上下文相关性  (0/1，无图则跳过)
  5. text_faithfulness       - 文本忠实度       (0/1)
  6. image_faithfulness      - 图像忠实度       (0/1，无图则跳过)

输入 JSON（run_unidoc_gen.py 输出）每条记录需包含：
  query_id, query, reference_answer, generated_answer,
  retrieved_ids (list[str]), domain, question_type

使用示例（从项目根目录）：
  python -m evaluation.run_unidoc_score \\
    --input  data/rag_outputs/unidoc_gen/unidoc_gen_proposed_top5.json \\
    --output data/rag_outputs/unidoc_gen/unidoc_gen_proposed_top5_scored.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 路径 & 环境变量
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent
_env_path = _ROOT / "backend" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

sys.path.insert(0, str(_ROOT / "backend"))
sys.path.insert(0, str(_ROOT))


def _configure_utf8_stdio() -> None:
    for name in ("stdout", "stderr"):
        s = getattr(sys, name, None)
        if callable(getattr(s, "reconfigure", None)):
            s.reconfigure(encoding="utf-8", errors="replace")


_configure_utf8_stdio()

# 延迟导入（需要环境变量已就绪）
from evaluation.evaluators.evaluators_openai import (  # noqa: E402
    AnswerCorrectnessEvaluator,
    AnswerRelevancyEvaluator,
    TextContextRelevancyEvaluator,
    ImageContextRelevancyEvaluator,
    TextFaithfulnessEvaluator,
    ImageFaithfulnessEvaluator,
)

# ---------------------------------------------------------------------------
# 单条记录评分
# ---------------------------------------------------------------------------

DIMENSIONS = [
    "answer_correctness",
    "answer_relevancy",
    "text_context_relevancy",
    "image_context_relevancy",
    "text_faithfulness",
    "image_faithfulness",
]


def _safe_run(evaluator_cls, label: str, **kwargs) -> Dict[str, Any]:
    """调用评估器，捕获异常，返回 {grade, reason}。"""
    try:
        result = evaluator_cls(**kwargs).run_evaluation()
        return {"grade": int(result.get("grade", 0)), "reason": result.get("reason", "")}
    except Exception as e:
        return {"grade": -1, "reason": f"评估出错: {e}"}


def _load_first_image(record: Dict[str, Any]) -> Optional[str]:
    """从 retrieved_ids 加载第一张有效图片的 base64 字符串。"""
    from evaluation._generation_core import read_image_as_base64

    ids: List[str] = record.get("retrieved_ids", [])
    domain: str = record.get("domain", "crossdomain")
    if not ids:
        return None

    # 优先尝试从 ChromaDB 获取 file_path
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        from app.core.config import settings as app_settings

        client = chromadb.Client(
            ChromaSettings(is_persistent=True, persist_directory=app_settings.CHROMA_PERSIST_DIR)
        )
        candidate_collections = [
            f"unidoc_{domain}_proposed",
            f"unidoc_{domain}_clip",
            f"unidoc_{domain}_ocr",
            "unidoc_crossdomain_proposed",
            "unidoc_crossdomain_clip",
            "unidoc_crossdomain_ocr",
        ]
        for col_name in candidate_collections:
            try:
                col = client.get_collection(col_name)
                result = col.get(ids=[ids[0]], include=["metadatas"])
                if result["ids"] and result["metadatas"][0]:
                    fp = result["metadatas"][0].get("file_path", "")
                    if fp:
                        payload = read_image_as_base64(fp)
                        if payload:
                            return payload
            except Exception:
                continue
    except Exception:
        pass

    # 回退：直接用 id 作为相对路径
    subset_root = Path(__file__).parent.parent / "data" / "UniDoc-Bench-subset"
    candidate = subset_root / ids[0]
    if candidate.exists():
        payload = read_image_as_base64(str(candidate))
        if payload:
            return payload
    return None


def score_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """对单条记录运行全部6个评估维度，结果写回 record。"""
    question = record.get("query", "")
    reference = record.get("reference_answer", "")
    generated = record.get("generated_answer", "")
    context = ""  # gen 输出不含文本上下文，跳过文本维度
    first_image: Optional[str] = _load_first_image(record)

    if not generated or str(generated).startswith("[ERROR"):
        for dim in DIMENSIONS:
            record.setdefault(f"{dim}_grade", -1)
            record.setdefault(f"{dim}_reason", "生成失败，跳过评分")
        return record

    # 1. 答案正确性
    r = _safe_run(AnswerCorrectnessEvaluator, "answer_correctness",
                  user_query=question, generated_answer=generated, reference_answer=reference)
    record["answer_correctness_grade"] = r["grade"]
    record["answer_correctness_reason"] = r["reason"]

    # 2. 答案相关性
    r = _safe_run(AnswerRelevancyEvaluator, "answer_relevancy",
                  user_query=question, generated_answer=generated)
    record["answer_relevancy_grade"] = r["grade"]
    record["answer_relevancy_reason"] = r["reason"]

    # 3. 文本上下文相关性
    if context:
        r = _safe_run(TextContextRelevancyEvaluator, "text_context_relevancy",
                      user_query=question, context=context)
    else:
        r = {"grade": -1, "reason": "无文本上下文，跳过"}
    record["text_context_relevancy_grade"] = r["grade"]
    record["text_context_relevancy_reason"] = r["reason"]

    # 4. 图像上下文相关性
    if first_image:
        r = _safe_run(ImageContextRelevancyEvaluator, "image_context_relevancy",
                      user_query=question, image=first_image)
    else:
        r = {"grade": -1, "reason": "无检索图像，跳过"}
    record["image_context_relevancy_grade"] = r["grade"]
    record["image_context_relevancy_reason"] = r["reason"]

    # 5. 文本忠实度
    if context:
        r = _safe_run(TextFaithfulnessEvaluator, "text_faithfulness",
                      user_query=question, generated_answer=generated, context=context)
    else:
        r = {"grade": -1, "reason": "无文本上下文，跳过"}
    record["text_faithfulness_grade"] = r["grade"]
    record["text_faithfulness_reason"] = r["reason"]

    # 6. 图像忠实度
    if first_image:
        r = _safe_run(ImageFaithfulnessEvaluator, "image_faithfulness",
                      user_query=question, generated_answer=generated, image=first_image)
    else:
        r = {"grade": -1, "reason": "无检索图像，跳过"}
    record["image_faithfulness_grade"] = r["grade"]
    record["image_faithfulness_reason"] = r["reason"]

    return record


# ---------------------------------------------------------------------------
# 统计汇总
# ---------------------------------------------------------------------------

def compute_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按维度、domain、question_type 汇总各维度指标。

    - answer_correctness: 0-10分，报告平均分
    - 其余维度: YES/NO (grade=1/0)，报告通过率
    """
    summary: Dict[str, Any] = {"total_records": len(records)}

    for dim in DIMENSIONS:
        key = f"{dim}_grade"
        valid = [r[key] for r in records if r.get(key, -1) >= 0]
        if dim == "answer_correctness":
            summary[dim] = {
                "evaluated": len(valid),
                "avg_score": round(sum(valid) / len(valid), 4) if valid else None,
            }
        else:
            passed = [v for v in valid if v == 1]
            summary[dim] = {
                "evaluated": len(valid),
                "pass_rate": round(len(passed) / len(valid), 4) if valid else None,
            }

    # 按 domain / question_type 分组的 answer_correctness 平均分
    by_domain: Dict[str, List[int]] = defaultdict(list)
    by_qtype: Dict[str, List[int]] = defaultdict(list)
    for r in records:
        g = r.get("answer_correctness_grade", -1)
        if g >= 0:
            by_domain[r.get("domain", "unknown")].append(g)
            by_qtype[r.get("question_type", "unknown")].append(g)

    summary["answer_correctness_by_domain"] = {
        d: {"count": len(s), "avg_score": round(sum(s) / len(s), 4)}
        for d, s in sorted(by_domain.items())
    }
    summary["answer_correctness_by_question_type"] = {
        qt: {"count": len(s), "avg_score": round(sum(s) / len(s), 4)}
        for qt, s in sorted(by_qtype.items())
    }

    return summary


# ---------------------------------------------------------------------------
# 断点续传检查
# ---------------------------------------------------------------------------

def _already_scored(record: Dict[str, Any]) -> bool:
    """判断记录是否已完成全部有效维度的评分。"""
    return all(record.get(f"{dim}_grade", -1) >= 0 for dim in DIMENSIONS
               if record.get(f"{dim}_grade", None) is not None)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="UniDoc 生成器多维度 LLM 评分")
    parser.add_argument("--input", required=True, help="run_unidoc_gen.py 输出的 JSON 文件")
    parser.add_argument("--output", required=True, help="评分结果输出路径")
    parser.add_argument("--resume", action="store_true", help="断点续传：跳过已有完整评分的记录")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records: List[Dict[str, Any]] = json.loads(input_path.read_text(encoding="utf-8"))
    print(f"[score] 加载 {len(records)} 条记录，来自 {input_path}")

    # 断点续传：合并已有结果
    if args.resume and output_path.exists():
        existing = {r["query_id"]: r for r in json.loads(output_path.read_text(encoding="utf-8"))}
        for i, rec in enumerate(records):
            qid = rec.get("query_id")
            if qid in existing:
                records[i] = existing[qid]
        done = sum(1 for r in records if _already_scored(r))
        print(f"[score] 断点续传：已完成 {done} 条")

    for i, rec in enumerate(records):
        if args.resume and _already_scored(rec):
            continue
        qid = rec.get("query_id", "?")
        print(f"[score] {i+1}/{len(records)} query_id={qid}", flush=True)
        records[i] = score_record(rec)
        ac = records[i].get("answer_correctness_grade", -1)
        print(f"  answer_correctness={ac}")

        # 每5条保存一次
        if (i + 1) % 5 == 0:
            output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[score] 已保存评分结果到 {output_path}")

    summary = compute_summary(records)
    print("\n=== 评分汇总 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[score] 汇总已保存到 {summary_path}")


if __name__ == "__main__":
    main()
