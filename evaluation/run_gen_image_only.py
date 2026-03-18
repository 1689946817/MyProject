"""
生成器评估 — 第一组实验：纯图片知识库。

知识库只包含图片，无文档文本。

支持的方法：
  proposed        图片语义描述检索 → 传原始图片给 MLLM
  baseline_clip   多模态 embedding 检索 → 传原始图片给 MLLM
  baseline_ocr    OCR 文字检索 → 传原始图片给 MLLM
  text_summary_rag  proposed 检索 → 只传图片描述文字给 LLM
  ocr_text_rag      OCR 检索 → 只传 OCR 文字给 LLM
  no_rag            不检索，直接问 MLLM

使用示例（在项目根目录）：
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

from evaluation._generation_core import (
    ids_to_file_paths,
    read_image_as_base64,
    generate_with_images,
    run_generation,
)
from evaluation.datasets.coco_subset import CocoQuerySample, load_coco_subset
from evaluation.methods import (
    proposed_multimodal_rag,
    baseline_clip_retrieval,
    baseline_ocr_rag,
    no_rag,
    text_summary_rag,
    ocr_text_rag,
)

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
    if method == "no_rag":
        r = await no_rag.generate(sample.query)
    elif method == "text_summary_rag":
        r = await text_summary_rag.generate(sample.query, top_k=top_k)
    elif method == "ocr_text_rag":
        r = await ocr_text_rag.generate(sample.query, top_k=top_k)
    else:
        ids = _RETRIEVAL_FUNCS[method](sample.query, top_k=top_k)
        file_paths = ids_to_file_paths(ids)
        image_b64_list = [b for p in file_paths if (b := read_image_as_base64(p))]
        try:
            answer = await generate_with_images(sample.query, image_b64_list)
        except Exception as e:
            print(f"  [WARN] 生成失败: {e}")
            answer = ""
        r = {
            "generated_answer": answer,
            "context": "",
            "images": [image_b64_list[0]] if image_b64_list else [],
        }

    return {
        "user_query": sample.query,
        "reference_answer": sample.reference_answer,
        "generated_answer": r["generated_answer"],
        "context": r["context"],
        "image": r.get("images", []),
    }


def main() -> None:
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
