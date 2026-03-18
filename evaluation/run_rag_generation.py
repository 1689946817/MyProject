"""
RAG 生成脚本：对所有生成评估方法统一跑生成，输出供评估框架使用的 JSON 文件。

支持两组实验：
  - image_only_kb：纯图片知识库（只有图片，无文档）
  - multimodal_kb：多模态文档知识库（PDF/Word/Markdown，含文本+图片+表格）
    注：文档解析部分待后续实现，当前 extra_context 留空

支持的生成方法：
  检索器评估三基线（同时支持两组实验）：
    - proposed        检索图片语义描述向量 → 传原始图片给 MLLM
    - baseline_clip   多模态 embedding 检索 → 传原始图片给 MLLM
    - baseline_ocr    OCR 文字向量检索     → 传原始图片给 MLLM
  仅生成器评估基线：
    - text_summary_rag  proposed 检索 → 只传图片描述文字给 LLM（不传图片）
    - ocr_text_rag      OCR 检索     → 只传 OCR 文字给 LLM（不传图片）
    - no_rag            不检索       → 直接问 MLLM

输出格式（每条记录）：
  {
    "user_query": "...",
    "reference_answer": "...",
    "generated_answer": "...",
    "context": "...",        # 文字上下文（描述/OCR/文档段落）
    "image": ["base64..."]   # 传给 LLM 的图片列表（无图片时为 []）
  }

使用示例（在项目根目录）：
  # 纯图片知识库实验
  python -m evaluation.run_rag_generation \\
    --dataset-path data/coco_subset_eval.json \\
    --method proposed \\
    --kb-type image_only_kb \\
    --top-k 5 \\
    --output-dir data/rag_outputs

  # 多模态文档知识库实验
  python -m evaluation.run_rag_generation \\
    --dataset-path data/coco_subset_eval.json \\
    --method proposed \\
    --kb-type multimodal_kb \\
    --top-k 5 \\
    --output-dir data/rag_outputs
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from evaluation.datasets.coco_subset import CocoQuerySample, load_coco_subset
from evaluation.methods import (
    baseline_clip_retrieval,
    baseline_ocr_rag,
    proposed_multimodal_rag,
    no_rag,
    text_summary_rag,
    ocr_text_rag,
)

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from app.langchain_integration.models import get_chat_model  # noqa: E402
from app.langchain_integration.vectorstores import get_vector_store  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402

# 传图片给 MLLM 时使用的 prompt
_RAG_WITH_IMAGE_PROMPT = (
    "你是一个多模态知识库问答助手。你将看到若干张检索到的相关图像，"
    "以及用户提出的问题。请仔细观察这些图像的内容，基于图像中的视觉信息回答用户的问题。\n\n"
    "用户问题：{query}\n\n"
    "{extra_context_section}"
    "请基于图像内容进行回答，可以自然地引用相关图像，例如"根据第一张图像，可以看到……"。"
    "如果图像信息不足以回答某些部分，请明确说明不确定。"
)

_EXTRA_CONTEXT_SECTION = "参考文档内容：\n{extra_context}\n\n"

# 支持传图片的方法
_IMAGE_METHODS = {"proposed", "baseline_clip", "baseline_ocr"}

# 各方法对应的检索函数（返回图像 ID 列表）
_RETRIEVAL_FUNCS = {
    "proposed": proposed_multimodal_rag.retrieve,
    "baseline_clip": baseline_clip_retrieval.retrieve,
    "baseline_ocr": baseline_ocr_rag.retrieve,
}


def _ids_to_file_paths(ids: List[str]) -> List[str]:
    """将图像 ID 列表转换为文件路径列表（从 ChromaDB 元数据中查询）。"""
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from app.core.config import settings as app_settings

    client = chromadb.Client(
        ChromaSettings(is_persistent=True, persist_directory=app_settings.CHROMA_PERSIST_DIR)
    )
    collection_names = [
        "images_semantic_desc",
        "images_multimodal_embedding",
        "images_ocr_text",
    ]
    id_to_path: Dict[str, str] = {}
    for col_name in collection_names:
        try:
            col = client.get_collection(col_name)
            result = col.get(ids=ids, include=["metadatas"])
            for img_id, meta in zip(result["ids"], result["metadatas"]):
                if img_id not in id_to_path and meta and meta.get("file_path"):
                    id_to_path[img_id] = meta["file_path"]
        except Exception:
            continue
        if len(id_to_path) == len(ids):
            break
    return [id_to_path.get(i, "") for i in ids]


def _read_image_as_base64(file_path: str) -> Optional[str]:
    if not file_path or not os.path.exists(file_path):
        return None
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def _generate_with_images(
    query: str,
    image_b64_list: List[str],
    extra_context: Optional[str] = None,
) -> str:
    """将检索到的图像（+ 可选文档上下文）送入 MLLM 生成答案。"""
    if not image_b64_list:
        return "未找到相关图像，无法回答问题。"

    extra_section = (
        _EXTRA_CONTEXT_SECTION.format(extra_context=extra_context)
        if extra_context else ""
    )
    prompt_text = _RAG_WITH_IMAGE_PROMPT.format(query=query, extra_context_section=extra_section)

    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt_text}]
    for idx, b64 in enumerate(image_b64_list, start=1):
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        content.append({"type": "text", "text": f"\n[图像 {idx}]"})

    model = get_chat_model()
    result = await model._agenerate([HumanMessage(content=content)])
    return result.generations[0].message.content


def _get_extra_context(kb_type: str, query: str, top_k: int) -> Optional[str]:
    """
    多模态文档知识库场景下，检索文本段落作为额外上下文。
    当前文档解析待实现，暂返回 None。
    """
    if kb_type != "multimodal_kb":
        return None
    # TODO: 文档解析实现后，在此处检索文本知识库并返回段落
    return None


async def _run_one_sample(
    sample: CocoQuerySample,
    method: str,
    kb_type: str,
    top_k: int,
) -> Dict[str, Any]:
    """对单条样本执行生成，返回结果记录。"""
    extra_context = _get_extra_context(kb_type, sample.query, top_k)

    # 不需要检索的方法
    if method == "no_rag":
        result = await no_rag.generate(sample.query)
        return {
            "user_query": sample.query,
            "reference_answer": sample.reference_answer,
            "generated_answer": result["generated_answer"],
            "context": result["context"],
            "image": result["images"],
        }

    if method == "text_summary_rag":
        result = await text_summary_rag.generate(sample.query, top_k=top_k, extra_context=extra_context)
        return {
            "user_query": sample.query,
            "reference_answer": sample.reference_answer,
            "generated_answer": result["generated_answer"],
            "context": result["context"],
            "image": result["images"],
        }

    if method == "ocr_text_rag":
        result = await ocr_text_rag.generate(sample.query, top_k=top_k, extra_context=extra_context)
        return {
            "user_query": sample.query,
            "reference_answer": sample.reference_answer,
            "generated_answer": result["generated_answer"],
            "context": result["context"],
            "image": result["images"],
        }

    # 传图片的方法：proposed / baseline_clip / baseline_ocr
    ids = _RETRIEVAL_FUNCS[method](sample.query, top_k=top_k)
    file_paths = _ids_to_file_paths(ids)
    image_b64_list = [b for p in file_paths if (b := _read_image_as_base64(p))]
    context = extra_context or ""

    try:
        answer = await _generate_with_images(sample.query, image_b64_list, extra_context=extra_context)
    except Exception as e:
        print(f"  [WARN] 生成失败: {e}")
        answer = ""

    return {
        "user_query": sample.query,
        "reference_answer": sample.reference_answer,
        "generated_answer": answer,
        "context": context,
        "image": [image_b64_list[0]] if image_b64_list else [],
    }


async def run_generation(
    samples: List[CocoQuerySample],
    method: str,
    kb_type: str,
    top_k: int,
    output_path: Path,
) -> None:
    records = []
    total = len(samples)
    for i, sample in enumerate(samples, start=1):
        print(f"[{i}/{total}] method={method}  kb={kb_type}  query={sample.query[:60]}")
        record = await _run_one_sample(sample, method, kb_type, top_k)
        records.append(record)
        output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done. {len(records)} records saved to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAG generation for evaluation.")
    parser.add_argument("--dataset-path", type=str, required=True)
    parser.add_argument(
        "--method",
        type=str,
        choices=["proposed", "baseline_clip", "baseline_ocr",
                 "text_summary_rag", "ocr_text_rag", "no_rag"],
        required=True,
        help=(
            "生成方法：\n"
            "  proposed / baseline_clip / baseline_ocr — 检索图片，传原始图片给 MLLM\n"
            "  text_summary_rag — 检索图片，只传描述文字给 LLM\n"
            "  ocr_text_rag     — OCR 检索，只传 OCR 文字给 LLM\n"
            "  no_rag           — 不检索，直接问 MLLM"
        ),
    )
    parser.add_argument(
        "--kb-type",
        type=str,
        choices=["image_only_kb", "multimodal_kb"],
        default="image_only_kb",
        help=(
            "知识库类型：\n"
            "  image_only_kb  — 纯图片知识库（第二组实验）\n"
            "  multimodal_kb  — 多模态文档知识库，含文本+图片+表格（第一组实验，文档解析待实现）"
        ),
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output-dir", type=str, default="data/rag_outputs")
    args = parser.parse_args()

    samples = load_coco_subset(args.dataset_path)
    if not samples:
        print("No samples loaded, check --dataset-path.")
        return

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"rag_output_{args.method}_{args.kb_type}.json"

    asyncio.run(run_generation(samples, args.method, args.kb_type, args.top_k, output_path))


if __name__ == "__main__":
    main()
