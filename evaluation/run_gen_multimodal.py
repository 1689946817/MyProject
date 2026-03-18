"""
生成器评估 — 第二组实验：多模态文档知识库。

知识库包含 PDF/Word/Markdown 等多模态文档（含文本、图片、表格）。
在图片检索的基础上，额外检索文本知识库段落作为补充上下文。

注：文档解析与文本知识库检索部分待后续实现（_get_text_context 中标有 TODO）。

支持的方法：
  proposed        图片语义描述检索 → 传原始图片 + 文档文本给 MLLM
  baseline_clip   多模态 embedding 检索 → 传原始图片 + 文档文本给 MLLM
  baseline_ocr    OCR 文字检索 → 传原始图片 + 文档文本给 MLLM
  text_summary_rag  proposed 检索 → 传图片描述文字 + 文档文本给 LLM
  ocr_text_rag      OCR 检索 → 传 OCR 文字 + 文档文本给 LLM
  text_kb_rag       仅检索文本知识库 → 传文档文本给 LLM（忽略图片）
  no_rag            不检索，直接问 MLLM

使用示例（在项目根目录）：
  python -m evaluation.run_gen_multimodal \\
    --dataset-path data/coco_subset_eval.json \\
    --method proposed \\
    --top-k 5 \\
    --output-dir data/rag_outputs/multimodal_kb
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


def _get_text_context(query: str, top_k: int) -> Optional[str]:
    """
    从文本知识库检索相关段落。
    TODO: 文档解析实现后在此处接入文本知识库检索逻辑。
    """
    return None


async def _run_one_sample(
    sample: CocoQuerySample,
    method: str,
    top_k: int,
) -> Dict[str, Any]:
    text_context = _get_text_context(sample.query, top_k)

    if method == "no_rag":
        r = await no_rag.generate(sample.query)
        return {
            "user_query": sample.query,
            "reference_answer": sample.reference_answer,
            "generated_answer": r["generated_answer"],
            "context": r["context"],
            "image": r.get("images", []),
        }

    if method == "text_kb_rag":
        # 仅文本知识库，忽略图片
        from evaluation.methods import text_summary_rag as _tsrag
        import sys
        from pathlib import Path as _Path
        sys.path.insert(0, str(_Path(__file__).parent.parent / "backend"))
        from app.langchain_integration.models import get_chat_model  # noqa: E402
        from langchain_core.messages import HumanMessage  # noqa: E402

        context = text_context or ""
        _PROMPT = (
            "你是一个知识库问答助手。以下是从文本知识库中检索到的相关内容，"
            "请基于这些内容回答用户的问题。\n\n"
            "检索到的内容：\n{context}\n\n"
            "用户问题：{query}\n\n"
            "如果信息不足以回答某些部分，请明确说明不确定。"
        )
        model = get_chat_model()
        result = await model._agenerate(
            [HumanMessage(content=_PROMPT.format(context=context, query=sample.query))]
        )
        return {
            "user_query": sample.query,
            "reference_answer": sample.reference_answer,
            "generated_answer": result.generations[0].message.content,
            "context": context,
            "image": [],
        }

    if method == "text_summary_rag":
        r = await text_summary_rag.generate(sample.query, top_k=top_k, extra_context=text_context)
    elif method == "ocr_text_rag":
        r = await ocr_text_rag.generate(sample.query, top_k=top_k, extra_context=text_context)
    else:
        # proposed / baseline_clip / baseline_ocr — 传图片
        ids = _RETRIEVAL_FUNCS[method](sample.query, top_k=top_k)
        file_paths = ids_to_file_paths(ids)
        image_b64_list = [b for p in file_paths if (b := read_image_as_base64(p))]
        try:
            answer = await generate_with_images(sample.query, image_b64_list, extra_context=text_context)
        except Exception as e:
            print(f"  [WARN] 生成失败: {e}")
            answer = ""
        r = {
            "generated_answer": answer,
            "context": text_context or "",
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
    parser = argparse.ArgumentParser(description="生成器评估 — 第二组：多模态文档知识库")
    parser.add_argument("--dataset-path", type=str, required=True)
    parser.add_argument(
        "--method",
        type=str,
        choices=["proposed", "baseline_clip", "baseline_ocr",
                 "text_summary_rag", "ocr_text_rag", "text_kb_rag", "no_rag"],
        required=True,
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output-dir", type=str, default="data/rag_outputs/multimodal_kb")
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
