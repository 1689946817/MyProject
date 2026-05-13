"""
生成器评估 — UniDoc-Bench-subset 数据集（实时逐条推理版）。

================================================================================
脚本用途
================================================================================
本脚本对 UniDoc-Bench-subset 数据集中的每条查询，实时调用 MLLM API 生成答案，
用于评估不同检索方法在多模态 RAG 场景下的生成质量。

工作流程：
  1. 加载 UniDoc-Bench-subset 的 8 个领域数据（每领域 100 条 QA）
  2. 根据指定方法，从跨领域候选池（crossdomain）检索 top-k 张图片
  3. 将检索到的图片 + 用户问题一起发给 MLLM，生成回答
  4. 将生成结果与 ground-truth 保存为 JSON 文件

================================================================================
支持的检索方法
================================================================================
  proposed        本系统方法：MLLM 语义描述 → 文本 Embedding 检索 → 传原始图片给 MLLM
  baseline_clip   基线方法：qwen3-vl-embedding 多模态检索 → 传原始图片给 MLLM
  baseline_ocr    基线方法：OCR 文字 → 文本 Embedding 检索 → 传原始图片给 MLLM
  no_rag          对照组：不检索，直接问 MLLM（无外部知识）

================================================================================
输入输出
================================================================================
输入：
  --subset-root   UniDoc-Bench-subset 数据目录（含 8 个领域的 parquet 文件）
  --domains       可选，指定评测哪些领域（默认全部 8 个）

输出：
  --output-dir/   输出目录
  unidoc_gen_{method}_top{k}.json   每条记录包含 query_id, query, domain,
                                    reference_answer, generated_answer, retrieved_ids 等

================================================================================
断点续传
================================================================================
脚本以 (query, domain) 作为去重键。如果输出文件已存在，会自动跳过已完成的样本，
支持中断后从中断处继续。

================================================================================
使用示例（从项目根目录）
================================================================================
  # proposed 方法，检索 top-5 图片
  python -m evaluation.run_unidoc_gen \\
    --method proposed \\
    --top-k 5 \\
    --output-dir data/rag_outputs/unidoc_gen

  # 仅评测特定领域
  python -m evaluation.run_unidoc_gen \\
    --method baseline_clip \\
    --domains finance healthcare
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

# ============================================================================
# 环境变量加载
# ============================================================================
# 脚本独立于 FastAPI 后端运行，需要手动加载 .env 中的模型配置
# （MLLM_BASE_URL, MLLM_API_KEY, EMBEDDING_BASE_URL 等）
_env_path = Path(__file__).parent.parent / "backend" / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

# ============================================================================
# 核心依赖导入
# ============================================================================
from evaluation._generation_core import (  # noqa: E402
    read_image_as_base64,      # 读取图片文件并编码为 base64 字符串
    generate_with_images,      # 将图片 + 问题发送给 MLLM 生成回答
)
from evaluation.datasets.unidoc_subset import (  # noqa: E402
    DOMAINS,                   # 8 个领域名称列表
    UniDocQuerySample,         # 单条查询样本的数据结构
    load_unidoc_domain,        # 从 parquet 文件加载指定领域的样本
)
from evaluation.methods import unidoc_clip, unidoc_ocr, unidoc_proposed  # noqa: E402

# 跨领域候选池标识，所有方法统一使用 crossdomain 集合进行检索
CROSSDOMAIN_KEY = "crossdomain"


def _configure_utf8_stdio() -> None:
    """将 stdout/stderr 重新配置为 UTF-8 编码，避免 Windows 下中文输出乱码。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


_configure_utf8_stdio()


def _ids_to_file_paths_unidoc(ids: List[str], domain: str) -> List[str]:
    """
    将检索返回的图片 ID 列表转换为本地文件路径。

    查询策略（按优先级）：
      1. 从 ChromaDB 的 proposed/clip/ocr 三个集合中查询 metadata.file_path
      2. 回退到 data/UniDoc-Bench-subset/ 目录下按 ID 直接查找文件

    Args:
        ids: 检索返回的图片 ID 列表（如文件名或 UUID）
        domain: 领域标识（如 "crossdomain"）

    Returns:
        与 ids 顺序一致的文件路径列表，未找到的返回空字符串
    """
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from app.core.config import settings as app_settings

    client = chromadb.Client(
        ChromaSettings(is_persistent=True, persist_directory=app_settings.CHROMA_PERSIST_DIR)
    )
    id_to_path: Dict[str, str] = {}
    # 遍历三个可能的集合查找 file_path（不同方法建的集合都可能包含该 ID）
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
    # 回退策略：从 subset_root 目录下按文件名直接查找
    subset_root = Path(__file__).parent.parent / "data" / "UniDoc-Bench-subset"
    for img_id in ids:
        if img_id not in id_to_path:
            candidate = subset_root / img_id
            if candidate.exists():
                id_to_path[img_id] = str(candidate)
    return [id_to_path.get(i, "") for i in ids]


async def _generate_no_rag(query: str) -> str:
    """no_rag 方法：不进行任何检索，直接将问题发给 MLLM，作为对照基线。"""
    # 构造简单的问答 Prompt，不提供任何外部知识
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
    """
    处理单条查询样本：检索 + 生成。

    流程：
      1. 生成 query_id（跨脚本一致的 16 位 MD5 哈希）
      2. 若为 no_rag，跳过检索直接生成
      3. 否则按方法检索 top-k 图片 ID，解析为文件路径，编码为 base64
      4. 将图片 + 问题发给 MLLM 生成回答
      5. 返回包含 query_id、query、domain、generated_answer 等的记录字典

    Args:
        sample: 单条 UniDoc 查询样本
        method: 检索方法名（proposed / baseline_clip / baseline_ocr / no_rag）
        top_k: 检索返回的图片数量

    Returns:
        包含完整评测信息的记录字典
    """
    # query_id 生成规则：md5("query||domain")[:16]
    # 该规则在 run_unidoc_gen_batch.py / run_unidoc_score.py 中保持一致，确保跨脚本可关联
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

    # 将图片 ID 解析为本地文件路径
    file_paths = _ids_to_file_paths_unidoc(ids, domain=CROSSDOMAIN_KEY)
    # 读取图片并编码为 base64，过滤掉读取失败的（payload 为空的被 walrus 运算符丢弃）
    image_payloads = [payload for p in file_paths if (payload := read_image_as_base64(p))]

    try:
        # 将图片 + 问题发送给 MLLM 生成回答
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
    """加载已有的输出文件，用于断点续传。文件不存在或解析失败时返回空列表。"""
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
    """
    批量运行生成评估，支持断点续传。

    逐条处理样本，每完成一条立即写入 JSON 文件（避免中途丢失进度）。
    以 (query, domain) 二元组作为去重键，跳过已完成的样本。

    Args:
        samples: 待评测的查询样本列表
        method: 检索方法名
        top_k: 检索图片数量
        output_path: 输出 JSON 文件路径
    """
    existing = _load_existing(output_path)
    # 用 (query, domain) 作为去重键，已处理的样本直接跳过
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


# ============================================================================
# 命令行入口
# ============================================================================
def main() -> None:
    """解析命令行参数，加载数据集，运行生成评估。"""
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
    domains = args.domains or DOMAINS  # 默认使用全部 8 个领域

    # ---- 加载所有领域的查询样本 ----
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

    # ---- OCR 方法前置检查：确保 crossdomain 集合的 OCR 索引已构建 ----
    if args.method == "baseline_ocr" and not unidoc_ocr.check_index(CROSSDOMAIN_KEY):
        print(
            "[ERROR] OCR index for crossdomain is missing or unhealthy. "
            "Rebuild it with `python -m evaluation.run_unidoc_full_eval --method baseline_ocr --build-index` first."
        )
        return

    print(f"Total samples: {len(samples)}")

    # ---- 构造输出路径并运行 ----
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # 输出文件名格式：unidoc_gen_{method}_top{k}.json
    output_path = output_dir / f"unidoc_gen_{args.method}_top{args.top_k}.json"

    asyncio.run(run_generation(samples, args.method, args.top_k, output_path))


if __name__ == "__main__":
    main()
