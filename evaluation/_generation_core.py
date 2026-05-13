"""
生成评估公共逻辑：图片读取、MLLM 调用、结果写入。

本模块抽取了多个生成评估脚本的公共代码，避免重复：
  - 图片 base64 编码与 MIME 类型推断
  - 从 ChromaDB 查询图像 ID 对应的文件路径
  - 构造多模态 Prompt 并调用 MLLM 生成答案
  - 通用的逐样本生成循环（run_generation）

被以下脚本引用：
  - run_gen_image_only.py（纯图片知识库生成）
  - run_gen_multimodal.py（多模态文档知识库生成）
"""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 将 backend 目录加入 sys.path，以便导入 app 下的模块
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from app.langchain_integration.models import get_chat_model  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402

from evaluation.datasets.coco_subset import CocoQuerySample, load_coco_subset  # noqa: E402

# ---- Prompt 模板 ----

# 传图片给 MLLM 时使用的 RAG Prompt 模板
# {query} 会被替换为用户问题，{extra_context_section} 为可选的文档上下文段落
_RAG_WITH_IMAGE_PROMPT = (
    "你是一个多模态知识库问答助手。你将看到若干张检索到的相关图像，"
    "以及用户提出的问题。请仔细观察这些图像的内容，基于图像中的视觉信息回答用户的问题。\n\n"
    "用户问题：{query}\n\n"
    "{extra_context_section}"
    "请基于图像内容进行回答，可以自然地引用相关图像，例如'根据第一张图像，可以看到……'。"
    "如果图像信息不足以回答某些部分，请明确说明不确定。"
)
# 文档上下文段落模板，仅在提供了 extra_context 时拼入主 Prompt
_EXTRA_CONTEXT_SECTION = "参考文档内容：\n{extra_context}\n\n"


# ---- 工具函数 ----

def _build_image_data_url(image_b64: str, file_path: str = "") -> str:
    """将 base64 编码的图片转为 data URL 格式，供 MLLM API 使用。

    Args:
        image_b64: 图片的 base64 编码字符串（不含 data URL 前缀）。
        file_path: 原始文件路径，用于推断 MIME 类型；为空时默认 image/jpeg。

    Returns:
        形如 "data:image/jpeg;base64,xxxxx" 的 data URL 字符串。
    """
    mime_type, _ = mimetypes.guess_type(file_path) if file_path else (None, None)
    actual_mime_type = mime_type if mime_type and mime_type.startswith("image/") else "image/jpeg"
    return f"data:{actual_mime_type};base64,{image_b64}"


def ids_to_file_paths(ids: List[str]) -> List[str]:
    """将图像 ID 列表转换为文件路径列表（从 ChromaDB 元数据中查询）。

    遍历多个 ChromaDB 集合（proposed / multimodal / ocr），从 metadata 的 file_path
    字段中查找每个 ID 对应的本地文件路径。一旦所有 ID 都找到即提前退出。

    Args:
        ids: 图像 ID 列表（UUID 字符串）。

    Returns:
        与 ids 等长的文件路径列表，未找到的 ID 对应空字符串。
    """
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from app.core.config import settings as app_settings

    client = chromadb.Client(
        ChromaSettings(is_persistent=True, persist_directory=app_settings.CHROMA_PERSIST_DIR)
    )
    id_to_path: Dict[str, str] = {}
    # 依次查询三个集合，优先从 proposed 集合中查找
    for col_name in [
        app_settings.COCO_PROPOSED_COLLECTION_NAME,
        "images_multimodal_embedding",
        "images_ocr_text",
    ]:
        try:
            col = client.get_collection(col_name)
            result = col.get(ids=ids, include=["metadatas"])
            for img_id, meta in zip(result["ids"], result["metadatas"]):
                if img_id not in id_to_path and meta and meta.get("file_path"):
                    id_to_path[img_id] = meta["file_path"]
        except Exception:
            continue
        # 所有 ID 都已找到，提前退出
        if len(id_to_path) == len(ids):
            break
    return [id_to_path.get(i, "") for i in ids]


def read_image_as_base64(file_path: str) -> Optional[tuple[str, str]]:
    """读取本地图片文件并返回 base64 编码。

    Args:
        file_path: 图片文件的本地路径。

    Returns:
        成功时返回 (base64字符串, file_path) 的元组；文件不存在时返回 None。
    """
    if not file_path or not os.path.exists(file_path):
        return None
    with open(file_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    return image_b64, file_path


# ---- MLLM 生成 ----

async def generate_with_images(
    query: str,
    image_payloads: List[tuple[str, str]],
    extra_context: Optional[str] = None,
) -> str:
    """将检索到的图像（+ 可选文档上下文）送入 MLLM 生成答案。

    构造包含文本 Prompt 和多张图片的多模态消息，调用 MLLM 获取回答。

    Args:
        query: 用户问题文本。
        image_payloads: 图片列表，每项为 (base64字符串, file_path) 的元组。
        extra_context: 可选的文档上下文文本，拼入 Prompt 中。

    Returns:
        MLLM 生成的回答文本。无图片时返回固定提示语。
    """
    if not image_payloads:
        return "未找到相关图像，无法回答问题。"

    # 拼接可选的文档上下文段落
    extra_section = (
        _EXTRA_CONTEXT_SECTION.format(extra_context=extra_context) if extra_context else ""
    )
    prompt_text = _RAG_WITH_IMAGE_PROMPT.format(query=query, extra_context_section=extra_section)

    # 构造多模态消息：先放文本 Prompt，再逐张附加图片和序号标记
    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt_text}]
    for idx, (image_b64, file_path) in enumerate(image_payloads, start=1):
        content.append({"type": "image_url", "image_url": {"url": _build_image_data_url(image_b64, file_path)}})
        content.append({"type": "text", "text": f"\n[图像 {idx}]"})

    model = get_chat_model()
    result = await model._agenerate([HumanMessage(content=content)])
    return result.generations[0].message.content


# ---- 通用生成循环 ----

async def run_generation(
    samples: List[CocoQuerySample],
    method: str,
    top_k: int,
    output_path: Path,
    run_one_sample,  # callable: async (sample, method, top_k) -> dict
) -> None:
    """通用的逐样本生成循环，将结果实时写入 JSON 文件。

    该函数负责遍历所有样本、调用调用方传入的 run_one_sample 回调完成推理，
    并在每条样本完成后立即持久化结果，防止中断丢失。

    Args:
        samples: 待评估的样本列表。
        method: 评估方法名称（如 "proposed"、"baseline_clip"）。
        top_k: 检索返回的 Top-K 数量。
        output_path: 输出 JSON 文件路径。
        run_one_sample: 异步回调函数，签名 async (sample, method, top_k) -> dict。
    """
    records = []
    total = len(samples)
    for i, sample in enumerate(samples, start=1):
        print(f"[{i}/{total}] method={method}  query={sample.query[:60]}")
        record = await run_one_sample(sample, method, top_k)
        records.append(record)
        # 每条样本完成后立即写入，防止中途丢失
        output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Done. {len(records)} records saved to {output_path}")
