"""
Baseline B：跨模态嵌入（CLIP / BLIP-2 Embedding）检索。

本文件只提供方法接口与占位实现，方便后续你接入具体的 CLIP / BLIP-2 模型。
默认实现会抛出 NotImplementedError，避免误用。
"""

from __future__ import annotations

from typing import List


def retrieve_text(query: str, top_k: int = 10) -> List[str]:
    """
    文本→图像检索（CLIP 文本编码 + 图像向量库）。

    需要你后续接入具体的跨模态嵌入模型与索引构建逻辑。
    返回 top_k 个预测图像 ID。
    """
    raise NotImplementedError(
        "baseline_clip_retrieval.retrieve_text 尚未实现，请接入 CLIP/BLIP-2 向量索引后填充。"
    )


def retrieve_image(image_path: str, top_k: int = 10) -> List[str]:
    """
    图像→图像检索（CLIP 图像编码 + 图像向量库）。
    """
    raise NotImplementedError(
        "baseline_clip_retrieval.retrieve_image 尚未实现，请接入 CLIP/BLIP-2 向量索引后填充。"
    )

