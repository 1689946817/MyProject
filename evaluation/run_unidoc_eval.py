"""
UniDoc-Bench-subset 离线检索评测脚本（单领域评测）。

功能概述：
    本脚本对 UniDoc-Bench-subset 数据集中单个领域（如 finance、energy 等）的
    图片检索效果进行离线评测。支持三种评测方法的对比实验：
    - proposed:     MLLM（多模态大模型）生成图片描述 → 文本 Embedding 检索（本文方法）
    - baseline_clip: 直接使用 CLIP 类多模态 Embedding 检索（基线方法）
    - baseline_ocr:  OCR 提取文本 → 文本 Embedding 检索（基线方法）

评测流程：
    1. 加载指定领域的 query 样本和候选图片集
    2. 可选：构建/重建该领域的检索索引（--build-index）
    3. 对每条 query 执行检索，记录排序结果
    4. 计算 Recall@K、MRR、mAP 等标准检索指标
    5. 按 question_type / answer_type 分组统计，分析不同子类别的表现差异
    6. 将结果保存为 JSON 文件

与 run_unidoc_full_eval.py 的区别：
    - 本脚本：单领域候选池，domain 内图片互相检索
    - run_unidoc_full_eval.py：跨领域混合候选池，所有 8 个领域的图片合并后检索

索引命名规则：
    ChromaDB 集合名 = unidoc_{domain}_{method}，例如：
    - unidoc_finance_proposed
    - unidoc_energy_baseline_clip
    - unidoc_education_baseline_ocr

使用示例（从项目根目录）：

    # 评测 proposed 方法在 finance 领域的表现
    python -m evaluation.run_unidoc_eval \\
        --domain finance \\
        --method proposed \\
        --top-k 10 \\
        --build-index

    # 评测 baseline_ocr 方法，跳过索引构建（假设索引已存在）
    python -m evaluation.run_unidoc_eval \\
        --domain energy \\
        --method baseline_ocr \\
        --top-k 10

结果文件：
    保存到 data/eval_results/unidoc_{domain}_{method}_{timestamp}.json
    包含：
    - summary: 汇总统计（Recall@1/@5/@K、MRR、mAP、延迟的均值+标准差）
    - by_question_type: 按问题类型分组的指标
    - by_answer_type: 按答案类型分组的指标
    - per_query: 每条 query 的逐条指标（首次命中位置、hit_flags、延迟等）
    - meta: 实验元信息（时间戳、方法、领域、top_k）
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# ──────────────────────────────────────────────────────────────────────
# 环境配置加载
# 评测脚本独立于 FastAPI 后端服务运行，但仍需读取 .env 中的模型 API 配置
# （如 EMBEDDING_BASE_URL、MLLM_BASE_URL 等），因此手动加载环境变量。
# ──────────────────────────────────────────────────────────────────────
_env_path = Path(__file__).parent.parent / "backend" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from evaluation.datasets.unidoc_subset import (  # noqa: E402
    DOMAINS,                # 8 个领域名称列表
    UniDocQuerySample,      # query 样本数据类（含 query、relevant_ids、question_type 等）
    get_domain_image_records,  # 加载某领域的候选图片元数据
    load_unidoc_domain,     # 加载某领域的 query 样本
)
from evaluation.metrics import (  # noqa: E402
    RankedList,             # 排序结果数据类（predicted_ids + relevant_ids）
    average_precision,      # 平均精度（AP）
    recall_at_k,            # Recall@K 指标
    reciprocal_rank,        # 倒数排名（RR / MRR 的基础）
)
from evaluation.methods import unidoc_clip, unidoc_ocr, unidoc_proposed  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# 工具函数：控制台安全输出
# Windows 终端编码可能不是 UTF-8，对特殊字符（如 ±）做编码转换避免报错
# ──────────────────────────────────────────────────────────────────────

def _configure_utf8_stdio() -> None:
    """将 stdout/stderr 重新配置为 UTF-8 编码，避免 Windows 下 print 报错。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


_configure_utf8_stdio()


def _safe_console_text(text: str) -> str:
    """将文本编码后重新解码，替换无法在当前终端编码中表示的字符。"""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def _print_safe(*parts: object, sep: str = " ", end: str = "\n") -> None:
    """安全打印：先经过编码清洗再输出。"""
    message = sep.join(str(part) for part in parts)
    print(_safe_console_text(message), end=end)


# ──────────────────────────────────────────────────────────────────────
# 工具函数：指标计算辅助
# ──────────────────────────────────────────────────────────────────────

def _first_hit_rank(ranked: RankedList) -> int | None:
    """返回排序列表中第一个命中的排名位置（1-based），无命中返回 None。

    用于衡量"用户需要看多少条结果才能找到正确答案"。
    """
    for idx, pid in enumerate(ranked.predicted_ids, start=1):
        if pid in ranked.relevant_ids:
            return idx
    return None


def _stats(values: List[float]) -> Dict[str, float]:
    """计算均值和标准差，返回 {"mean": ..., "std": ...}。

    标准差在样本数 <= 1 时返回 0.0，避免 statistics.stdev 抛出异常。
    """
    mean = sum(values) / len(values) if values else 0.0
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return {"mean": round(mean, 4), "std": round(std, 4)}


def _group_stats(records: List[Dict], group_key: str, top_k: int) -> Dict[str, Any]:
    """按指定字段分组统计检索指标。

    例如按 question_type 分组，可分析 "事实型" vs "推理型" 问题的检索效果差异。
    每组输出 Recall@1、Recall@5、Recall@K、MRR、mAP@K 的均值和标准差。
    """
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for r in records:
        groups[r[group_key]].append(r)

    result = {}
    for group_val, group_records in sorted(groups.items()):
        rr_vals = [r["reciprocal_rank"] for r in group_records]
        r1_vals = [r["recall_at_1"] for r in group_records]
        r5_vals = [r["recall_at_5"] for r in group_records]
        rk_vals = [r[f"recall_at_{top_k}"] for r in group_records]
        ap_vals = [r[f"ap_at_{top_k}"] for r in group_records]
        result[group_val] = {
            "count": len(group_records),
            "recall_at_1": _stats(r1_vals),
            "recall_at_5": _stats(r5_vals),
            f"recall_at_{top_k}": _stats(rk_vals),
            "mrr": _stats(rr_vals),
            f"map_at_{top_k}": _stats(ap_vals),
        }
    return result


# ──────────────────────────────────────────────────────────────────────
# 核心评测逻辑
# ──────────────────────────────────────────────────────────────────────

def run_experiment(
    domain: str,
    samples: List[UniDocQuerySample],
    method: str,
    top_k: int,
    output_dir: Path,
) -> None:
    """执行单领域检索评测实验。

    对 samples 中的每条 query 调用指定方法的 retrieve 接口，
    收集排序结果并计算各项检索指标，最终输出汇总和分组统计。

    Args:
        domain: 评测领域名称（如 "finance"），传递给 retrieve 方法以定位索引。
        samples: 该领域的 query 样本列表。
        method: 评测方法，必须为 "proposed" / "baseline_clip" / "baseline_ocr" 之一。
        top_k: 返回的检索结果数量上限。
        output_dir: 结果 JSON 文件的输出目录。
    """
    ranked_list: List[RankedList] = []
    per_query_records: List[Dict[str, Any]] = []

    for i, sample in enumerate(samples):
        t0 = time.perf_counter()

        # 根据方法选择对应的检索接口
        # proposed: MLLM 描述 → 文本向量检索
        # baseline_clip: 多模态向量直接检索
        # baseline_ocr: OCR 文本 → 文本向量检索
        if method == "proposed":
            predicted_ids = unidoc_proposed.retrieve(sample.query, domain=domain, top_k=top_k)
        elif method == "baseline_clip":
            predicted_ids = unidoc_clip.retrieve(sample.query, domain=domain, top_k=top_k)
        elif method == "baseline_ocr":
            predicted_ids = unidoc_ocr.retrieve(sample.query, domain=domain, top_k=top_k)
        else:
            raise ValueError(f"Unsupported method: {method}")

        latency_ms = (time.perf_counter() - t0) * 1000
        ranked = RankedList(predicted_ids=predicted_ids, relevant_ids=sample.relevant_ids)
        ranked_list.append(ranked)

        fhr = _first_hit_rank(ranked)
        # hit_flags: 排序列表中每个位置是否命中相关文档，用于后续分析
        hit_flags = [pid in sample.relevant_ids for pid in predicted_ids]

        per_query_records.append({
            "query_index": i,
            "query": sample.query,
            "domain": sample.domain,
            "question_type": sample.question_type,
            "answer_type": sample.answer_type,
            "relevant_ids": list(sample.relevant_ids),
            "predicted_ids": predicted_ids,
            "hit_flags": hit_flags,
            "hit_count": sum(hit_flags),
            "first_hit_rank": fhr,
            "recall_at_1": recall_at_k(ranked, 1),
            "recall_at_5": recall_at_k(ranked, 5),
            f"recall_at_{top_k}": recall_at_k(ranked, top_k),
            "reciprocal_rank": reciprocal_rank(ranked),
            f"ap_at_{top_k}": average_precision(ranked, top_k),
            "latency_ms": round(latency_ms, 2),
        })

        _print_safe(
            f"  [{i+1}/{len(samples)}] RR={reciprocal_rank(ranked):.2f}  "
            f"first_hit={fhr}  latency={latency_ms:.0f}ms  query={sample.query[:60]}"
        )

    # ── 汇总统计：计算所有 query 的整体指标均值和标准差 ──
    latencies = [r["latency_ms"] for r in per_query_records]
    summary = {
        "method": method,
        "domain": domain,
        "top_k": top_k,
        "num_queries": len(ranked_list),
        "recall_at_1": _stats([recall_at_k(r, 1) for r in ranked_list]),
        "recall_at_5": _stats([recall_at_k(r, 5) for r in ranked_list]),
        f"recall_at_{top_k}": _stats([recall_at_k(r, top_k) for r in ranked_list]),
        "mrr": _stats([reciprocal_rank(r) for r in ranked_list]),
        f"map_at_{top_k}": _stats([average_precision(r, top_k) for r in ranked_list]),
        "latency_ms": _stats(latencies),
        "latency_ms_median": round(statistics.median(latencies), 2),
    }

    # ── 分组统计：按 question_type / answer_type 细分分析 ──
    # 例如可发现 "数值型答案" 的检索效果是否优于 "文本型答案"
    by_question_type = _group_stats(per_query_records, "question_type", top_k)
    by_answer_type = _group_stats(per_query_records, "answer_type", top_k)

    # ── 控制台输出汇总结果 ──
    _print_safe(f"\n{'='*55}")
    _print_safe(f"Method: {method}  |  Domain: {domain}  |  Queries: {summary['num_queries']}  |  Top-K: {top_k}")
    _print_safe(f"{'='*55}")
    for k in (1, 5, top_k):
        key = f"recall_at_{k}"
        s = summary[key]
        _print_safe(f"Recall@{k}:   {s['mean']:.4f}  (±{s['std']:.4f})")
    _print_safe(f"MRR:         {summary['mrr']['mean']:.4f}  (±{summary['mrr']['std']:.4f})")
    _print_safe(f"mAP@{top_k}:     {summary[f'map_at_{top_k}']['mean']:.4f}  (±{summary[f'map_at_{top_k}']['std']:.4f})")
    _print_safe(
        f"Latency(ms): mean={summary['latency_ms']['mean']:.1f}  "
        f"median={summary['latency_ms_median']:.1f}  std={summary['latency_ms']['std']:.1f}"
    )

    _print_safe(f"\n--- By question_type ---")
    for qt, s in by_question_type.items():
        _print_safe(f"  {qt} (n={s['count']}): Recall@{top_k}={s[f'recall_at_{top_k}']['mean']:.4f}  MRR={s['mrr']['mean']:.4f}")

    _print_safe(f"\n--- By answer_type ---")
    for at, s in by_answer_type.items():
        _print_safe(f"  {at} (n={s['count']}): Recall@{top_k}={s[f'recall_at_{top_k}']['mean']:.4f}  MRR={s['mrr']['mean']:.4f}")

    # ── 保存结果到 JSON 文件 ──
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"unidoc_{domain}_{method}_{timestamp}.json"

    result = {
        "summary": summary,
        "by_question_type": by_question_type,
        "by_answer_type": by_answer_type,
        "per_query": per_query_records,
        "meta": {
            "timestamp": timestamp,
            "method": method,
            "domain": domain,
            "top_k": top_k,
        },
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_safe(f"\n结果已保存到: {output_path}")


def main() -> None:
    """命令行入口：解析参数、加载数据、可选构建索引、执行评测。"""
    parser = argparse.ArgumentParser(description="Offline retrieval evaluation on UniDoc-Bench subset.")
    parser.add_argument("--domain", type=str, required=True, choices=DOMAINS, help="要评测的领域名称")
    parser.add_argument(
        "--method",
        type=str,
        choices=["proposed", "baseline_clip", "baseline_ocr"],
        default="baseline_ocr",
        help="评测方法：proposed=本文方法, baseline_clip=多模态基线, baseline_ocr=OCR基线",
    )
    parser.add_argument("--top-k", type=int, default=10, help="检索返回的结果数量")
    parser.add_argument("--build-index", action="store_true", help="评测前先（重新）构建索引")
    parser.add_argument("--subset-root", type=str, default="data/UniDoc-Bench-subset", help="数据集根目录")
    parser.add_argument("--output-dir", type=str, default="data/eval_results", help="结果输出目录")
    parser.add_argument("--dataset-name", type=str, default="UniDoc-Bench-subset", help="数据集标识名，用于缓存签名")
    parser.add_argument("--cache-dir", type=str, default="data/cache/unidoc_proposed", help="proposed 方法的描述缓存目录")
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="复用已成功的 proposed 缓存记录（默认开启）。使用 --no-resume 禁用。",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="重试之前失败的 proposed 缓存记录（默认跳过失败记录）。",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="忽略已有缓存，强制重新生成所有 MLLM 描述。",
    )
    args = parser.parse_args()

    subset_root = Path(args.subset_root)
    output_dir = Path(args.output_dir)

    # ── 加载数据 ──
    print(f"Loading domain '{args.domain}' from {subset_root}...")
    samples = load_unidoc_domain(args.domain, subset_root)
    print(f"Loaded {len(samples)} queries.")

    # ── 构建或验证索引 ──
    if args.build_index:
        print(f"Building index for method '{args.method}'...")
        image_records = get_domain_image_records(args.domain, subset_root)
        print(f"Candidate images: {len(image_records)}")

        if args.method == "proposed":
            # proposed 方法的索引构建会调用 MLLM 生成图片描述，
            # 缓存机制（resume/retry_failed/force_refresh）控制是否复用已有结果
            print(
                "Proposed cache options: "
                f"resume={args.resume}  "
                f"retry_failed={args.retry_failed}  "
                f"force_refresh={args.force_refresh}  "
                f"dataset_name={args.dataset_name}  "
                f"cache_dir={args.cache_dir}"
            )
            unidoc_proposed.build_index(
                args.domain,
                image_records,
                dataset_name=args.dataset_name,
                cache_dir=args.cache_dir,
                resume=args.resume,
                retry_failed=args.retry_failed,
                force_refresh=args.force_refresh,
            )
        elif args.method == "baseline_clip":
            unidoc_clip.build_index(args.domain, image_records)
        elif args.method == "baseline_ocr":
            unidoc_ocr.build_index(args.domain, image_records)
    else:
        # 未指定 --build-index 时，检查索引是否已存在
        if args.method == "proposed":
            has_index = unidoc_proposed.check_index(args.domain)
        elif args.method == "baseline_clip":
            has_index = unidoc_clip.check_index(args.domain)
        else:
            has_index = unidoc_ocr.check_index(args.domain)

        if not has_index:
            print(f"[ERROR] Index for '{args.method}' domain '{args.domain}' is empty. "
                  "Run with --build-index first.")
            return

    print(f"\nRunning evaluation: method={args.method}  domain={args.domain}  top_k={args.top_k}")
    run_experiment(
        domain=args.domain,
        samples=samples,
        method=args.method,
        top_k=args.top_k,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    main()
