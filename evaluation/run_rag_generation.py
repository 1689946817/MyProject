"""
RAG 生成脚本：对四种检索方法统一跑生成，输出供评估框架使用的 JSON 文件。

流程：
  1. 读取 COCO 子集查询样本（含 reference_answer）
  2. 对每条查询，用指定检索方法取回 top-K 图像
  3. 将检索到的图像统一送入 MLLM（Qwen-VL）生成答案
  4. 输出 JSON 文件，格式与 evaluate_rag_pipeline.py 兼容

输出格式（每条记录）：
  {
    "user_query": "...",
    "reference_answer": "...",
    "generated_answer": "...",
    "context": "...",        # 检索到的图像描述文本，拼接而成
    "image": ["base64..."]   # 第一张检索图像的 base64（评估框架只取 [0]）
  }

使用示例（在项目根目录）：
  python -m evaluation.run_rag_generation \\
    --dataset-path data/coco_subset_eval.json \\
    --method proposed \\
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
    baseline_text_rag,
    proposed_multimodal_rag,
)

# 将 backend 加入路径，以便直接导入 app 模块
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from app.semantic.mllm_client import get_mllm_client  # noqa: E402


# RAG 生成时使用的 prompt，与 rag_engine.py 保持一致
_RAG_PROMPT = (
    "你是一个多模态知识库问答助手。你将看到若干张检索到的相关图像，"
    "以及用户提出的问题。请仔细观察这些图像的内容，基于图像中的视觉信息回答用户的问题。\n\n"
    "用户问题：{query}\n\n"
    "请基于图像内容进行回答，可以自然地引用相关图像，例如"根据第一张图像，可以看到……"。"
    "如果图像信息不足以回答某些部分，请明确说明不确定。"
)


def _retrieve(method: str, query: str, top_k: int) -> List[str]:
    """调用对应检索方法，返回图像 ID 列表。"""
    if method == "proposed":
        return proposed_multimodal_rag.retrieve(query, top_k=top_k)
    elif method == "baseline_text":
        return baseline_text_rag.retrieve(query, top_k=top_k)
    elif method == "baseline_clip":
        return baseline_clip_retrieval.retrieve(query, top_k=top_k)
    elif method == "baseline_ocr":
        return baseline_ocr_rag.retrieve(query, top_k=top_k)
    else:
        raise ValueError(f"Unsupported method: {method}")


def _ids_to_file_paths(ids: List[str]) -> List[str]:
    """
    将图像 ID 列表转换为文件路径列表。

    从 ChromaDB 的 proposed 集合（images_semantic_desc）查元数据，
    获取 file_path。其他基线集合的元数据格式相同，也包含 file_path。
    """
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from backend.app.core.config import settings as app_settings

    client = chromadb.Client(
        ChromaSettings(
            is_persistent=True,
            persist_directory=app_settings.CHROMA_PERSIST_DIR,
        )
    )

    # 依次尝试各集合，取到 file_path 即止
    collection_names = [
        "images_semantic_desc",
        "images_text_only",
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
    """读取图像文件，返回 base64 字符串；文件不存在则返回 None。"""
    if not file_path or not os.path.exists(file_path):
        return None
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def _generate_answer(query: str, image_b64_list: List[str]) -> str:
    """将检索到的图像送入 MLLM 生成答案。"""
    if not image_b64_list:
        return "未找到相关图像，无法回答问题。"

    mllm = get_mllm_client()
    content: List[Dict[str, Any]] = [
        {"type": "text", "text": _RAG_PROMPT.format(query=query)}
    ]
    for idx, b64 in enumerate(image_b64_list, start=1):
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
        content.append({"type": "text", "text": f"\n[图像 {idx}]"})

    return await mllm.chat_with_images(content=content)


async def run_generation(
    samples: List[CocoQuerySample],
    method: str,
    top_k: int,
    output_path: Path,
) -> None:
    records = []
    total = len(samples)

    for i, sample in enumerate(samples, start=1):
        print(f"[{i}/{total}] method={method}  query={sample.query[:60]}")

        # 1. 检索
        ids = _retrieve(method, sample.query, top_k)

        # 2. ID → 文件路径 → base64
        file_paths = _ids_to_file_paths(ids)
        image_b64_list = [b for p in file_paths if (b := _read_image_as_base64(p))]

        # 3. 生成答案
        try:
            answer = await _generate_answer(sample.query, image_b64_list)
        except Exception as e:
            print(f"  [WARN] 生成失败: {e}")
            answer = ""

        # 4. context：用文件路径列表拼成文本（评估框架用于 Text Faithfulness）
        context = "; ".join(p for p in file_paths if p)

        records.append({
            "user_query": sample.query,
            "reference_answer": sample.reference_answer,
            "generated_answer": answer,
            "context": context,
            "image": [image_b64_list[0]] if image_b64_list else [],
        })

        # 实时写入，防止中途中断丢失进度
        output_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"Done. {len(records)} records saved to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAG generation for all methods.")
    parser.add_argument("--dataset-path", type=str, required=True)
    parser.add_argument(
        "--method",
        type=str,
        choices=["proposed", "baseline_text", "baseline_clip", "baseline_ocr"],
        required=True,
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
    output_path = output_dir / f"rag_output_{args.method}.json"

    asyncio.run(run_generation(samples, args.method, args.top_k, output_path))


if __name__ == "__main__":
    main()
