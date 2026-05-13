"""
生成器评估 — 第一组实验：纯图片知识库。

================================================================================
脚本用途
================================================================================
本脚本评估"纯图片知识库"场景下的 RAG 生成质量。
知识库仅包含图片，不包含文档文本（区别于第二组多模态文档知识库实验）。

工作流程：
  1. 加载 COCO 子集评测数据集
  2. 根据指定方法检索 top-k 张图片
  3. 将检索到的图片 + 用户问题发给 MLLM（或仅文本给 LLM）生成回答
  4. 保存生成结果与 ground-truth

================================================================================
支持的检索方法
================================================================================
  proposed          本系统方法：MLLM 语义描述检索 → 传原始图片给 MLLM
  baseline_clip     基线方法：多模态 embedding 检索 → 传原始图片给 MLLM
  baseline_ocr      基线方法：OCR 文字检索 → 传原始图片给 MLLM
  text_summary_rag  proposed 检索 → 只传图片描述文字给 LLM（纯文本，无图片）
  ocr_text_rag      OCR 检索 → 只传 OCR 文字给 LLM（纯文本，无图片）
  no_rag            不检索，直接问 MLLM

================================================================================
输入输出
================================================================================
输入：
  --dataset-path    COCO 子集评测数据集 JSON 文件路径
  --method          检索方法名
  --top-k           检索返回的图片数量

输出：
  --output-dir/rag_output_{method}.json
  每条记录包含 user_query, reference_answer, generated_answer, context, image

================================================================================
使用示例（在项目根目录）
================================================================================
  python -m evaluation.run_gen_image_only \\
    --dataset-path data/coco_subset_eval.json \\
    --method proposed \\
    --top-k 5 \\
    --output-dir data/rag_outputs/image_only_kb
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

# ============================================================================
# 核心依赖导入
# ============================================================================
from evaluation._generation_core import (
    ids_to_file_paths,         # 将图片 ID 列表转为本地文件路径
    read_image_as_base64,      # 读取图片文件并编码为 base64
    generate_with_images,      # 将图片 + 问题发送给 MLLM 生成回答
    run_generation,            # 通用批量运行函数（支持断点续传）
)
from evaluation.datasets.coco_subset import CocoQuerySample, load_coco_subset
from evaluation.methods import (
    proposed_multimodal_rag,   # 本系统方法：MLLM 语义描述检索
    baseline_clip_retrieval,   # 基线方法：多模态 embedding 检索
    baseline_ocr_rag,          # 基线方法：OCR 文字检索
    no_rag,                    # 对照组：不检索
    text_summary_rag,          # 文本摘要 RAG（传描述文字给 LLM）
    ocr_text_rag,              # OCR 文本 RAG（传 OCR 文字给 LLM）
)

# 检索方法名 → 检索函数的映射（用于传图片的方法）
_RETRIEVAL_FUNCS = {
    "proposed": proposed_multimodal_rag.retrieve,
    "baseline_clip": baseline_clip_retrieval.retrieve,
    "baseline_ocr": baseline_ocr_rag.retrieve,
}


async def _run_one_sample(
    sample: CocoQuerySample,
    method: str,
    top_k: int,
) -> Dict[str, Any]:
    """
    处理单条查询样本：检索 + 生成（纯图片知识库版本）。

    方法分类：
      - no_rag：不检索，直接问 MLLM
      - text_summary_rag：检索后只传描述文字给 LLM（纯文本）
      - ocr_text_rag：检索后只传 OCR 文字给 LLM（纯文本）
      - proposed / baseline_clip / baseline_ocr：检索后传图片给 MLLM

    Args:
        sample: COCO 查询样本
        method: 检索方法名
        top_k: 检索图片数量

    Returns:
        包含 user_query, reference_answer, generated_answer, context, image 的记录
    """
    # ---- no_rag：不检索，直接问 MLLM ----
    if method == "no_rag":
        r = await no_rag.generate(sample.query)
    # ---- text_summary_rag / ocr_text_rag：纯文本 RAG，不传图片 ----
    elif method == "text_summary_rag":
        r = await text_summary_rag.generate(sample.query, top_k=top_k)
    elif method == "ocr_text_rag":
        r = await ocr_text_rag.generate(sample.query, top_k=top_k)
    else:
        # ---- proposed / baseline_clip / baseline_ocr：传图片给 MLLM ----
        ids = _RETRIEVAL_FUNCS[method](sample.query, top_k=top_k)
        file_paths = ids_to_file_paths(ids)
        image_payloads = [payload for p in file_paths if (payload := read_image_as_base64(p))]
        try:
            answer = await generate_with_images(sample.query, image_payloads)
        except Exception as e:
            print(f"  [WARN] 生成失败: {e}")
            answer = ""
        r = {
            "generated_answer": answer,
            "context": "",
            "images": [image_payloads[0][0]] if image_payloads else [],
        }

    return {
        "user_query": sample.query,
        "reference_answer": sample.reference_answer,
        "generated_answer": r["generated_answer"],
        "context": r["context"],
        "image": r.get("images", []),
    }


# ============================================================================
# 命令行入口
# ============================================================================
def main() -> None:
    """解析命令行参数，加载 COCO 数据集，运行纯图片知识库生成评估。"""
    parser = argparse.ArgumentParser(description="生成器评估 — 第一组：纯图片知识库")
    parser.add_argument("--dataset-path", type=str, required=True)
    parser.add_argument(
        "--method",
        type=str,
        choices=["proposed", "baseline_clip", "baseline_ocr",
                 "text_summary_rag", "ocr_text_rag", "no_rag"],
        required=True,
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output-dir", type=str, default="data/rag_outputs/image_only_kb")
    args = parser.parse_args()

    samples = load_coco_subset(args.dataset_path)
    if not samples:
        print("No samples loaded, check --dataset-path.")
        return

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"rag_output_{args.method}.json"

    asyncio.run(run_generation(samples, args.method, args.top_k, output_path, _run_one_sample))


if __name__ == "__main__":
    main()
