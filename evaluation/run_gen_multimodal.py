"""
生成器评估 — 第二组实验：多模态文档知识库。

================================================================================
脚本用途
================================================================================
本脚本评估"多模态文档知识库"场景下的 RAG 生成质量。
与第一组实验（纯图片知识库）的区别在于：除了图片检索外，
还额外检索文本知识库段落作为补充上下文传给 MLLM/LLM。

知识库内容：PDF/Word/Markdown 等多模态文档（含文本、图片、表格）。

注意：文档解析与文本知识库检索部分尚未实现（_get_text_context 中标有 TODO），
目前所有方法的 extra_context 均为 None。

================================================================================
支持的检索方法
================================================================================
  proposed          本系统方法：MLLM 语义描述检索 → 传原始图片 + 文档文本给 MLLM
  baseline_clip     基线方法：多模态 embedding 检索 → 传原始图片 + 文档文本给 MLLM
  baseline_ocr      基线方法：OCR 文字检索 → 传原始图片 + 文档文本给 MLLM
  text_summary_rag  proposed 检索 → 只传图片描述文字 + 文档文本给 LLM（纯文本）
  ocr_text_rag      OCR 检索 → 只传 OCR 文字 + 文档文本给 LLM（纯文本）
  text_kb_rag       仅检索文本知识库 → 只传文档文本给 LLM（忽略图片）
  no_rag            不检索，直接问 MLLM

================================================================================
输入输出
================================================================================
输入：
  --dataset-path    COCO 子集评测数据集 JSON 文件路径
  --method          检索方法名
  --top-k           检索返回的图片/文档数量

输出：
  --output-dir/rag_output_{method}.json
  每条记录包含 user_query, reference_answer, generated_answer, context, image

================================================================================
使用示例（在项目根目录）
================================================================================
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


def _get_text_context(query: str, top_k: int) -> Optional[str]:
    """
    从文本知识库检索与 query 相关的文档段落。

    目前尚未实现，始终返回 None。文档解析与文本向量检索完成后，
    应在此处接入检索逻辑，返回拼接后的文本段落。

    TODO: 实现文本知识库检索（解析 PDF/Word/Markdown → 分块 → Embedding → 检索）

    Args:
        query: 用户查询
        top_k: 返回的段落数量

    Returns:
        拼接后的相关文本段落，或 None
    """
    return None


async def _run_one_sample(
    sample: CocoQuerySample,
    method: str,
    top_k: int,
) -> Dict[str, Any]:
    """
    处理单条查询样本：检索 + 生成（多模态文档知识库版本）。

    与 run_gen_image_only.py 的区别：
      - 额外调用 _get_text_context() 获取文本知识库上下文
      - 将 text_context 作为 extra_context 传给生成函数
      - text_kb_rag 方法仅使用文本知识库，忽略图片

    Args:
        sample: COCO 查询样本
        method: 检索方法名
        top_k: 检索数量

    Returns:
        包含 user_query, reference_answer, generated_answer, context, image 的记录
    """
    # 获取文本知识库上下文（目前返回 None）
    text_context = _get_text_context(sample.query, top_k)

    # ---- no_rag：不检索，直接问 MLLM ----
    if method == "no_rag":
        r = await no_rag.generate(sample.query)
        return {
            "user_query": sample.query,
            "reference_answer": sample.reference_answer,
            "generated_answer": r["generated_answer"],
            "context": r["context"],
            "image": r.get("images", []),
        }

    # ---- text_kb_rag：仅使用文本知识库，不检索图片 ----
    if method == "text_kb_rag":
        # 仅文本知识库，忽略图片，直接用 text_context + query 调用 LLM
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

    # ---- text_summary_rag / ocr_text_rag：纯文本 RAG，传描述文字/OCR 文字给 LLM ----
    if method == "text_summary_rag":
        r = await text_summary_rag.generate(sample.query, top_k=top_k, extra_context=text_context)
    elif method == "ocr_text_rag":
        r = await ocr_text_rag.generate(sample.query, top_k=top_k, extra_context=text_context)
    else:
        # ---- proposed / baseline_clip / baseline_ocr：传图片给 MLLM ----
        ids = _RETRIEVAL_FUNCS[method](sample.query, top_k=top_k)
        file_paths = ids_to_file_paths(ids)
        image_payloads = [payload for p in file_paths if (payload := read_image_as_base64(p))]
        try:
            answer = await generate_with_images(sample.query, image_payloads, extra_context=text_context)
        except Exception as e:
            print(f"  [WARN] 生成失败: {e}")
            answer = ""
        r = {
            "generated_answer": answer,
            "context": text_context or "",
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
    """解析命令行参数，加载 COCO 数据集，运行多模态文档知识库生成评估。"""
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
