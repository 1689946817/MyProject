"""
RAG 引擎模块

该模块实现了检索增强生成（RAG）的核心逻辑，用于：
- 基于用户查询（文本或图像）检索相关图像
- 将检索到的原始图像传给多模态大模型生成回答

是实现多模态 RAG 问答的核心组件。
"""
import base64
import os
from typing import Any, Dict, List, Optional, Tuple

from fastapi import UploadFile

from app.application.dispatcher import image_to_image_search, text_to_image_search
from app.semantic.mllm_client import get_mllm_client


def _read_image_as_base64(file_path: str) -> str:
    """读取图像文件并转换为base64编码

    Args:
        file_path: 图像文件路径

    Returns:
        str: base64编码的图像数据
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"图像文件不存在: {file_path}")

    with open(file_path, "rb") as f:
        image_data = f.read()

    return base64.b64encode(image_data).decode("utf-8")




async def rag_chat(
    query: str,
    top_k: int = 5,
    image: Optional[UploadFile] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """RAG 问答主流程

    执行检索增强生成（RAG）的完整流程：
    1. 根据输入类型选择检索方式（文本检索或图像检索）
    2. 获取检索到的图像文件路径
    3. 将检索到的原始图像传给多模态大模型生成回答
    4. 返回生成的回答和检索结果

    Args:
        query: 用户问题
        top_k: 返回的检索结果数量，默认为 5
        image: 可选的上传图像，用于图像检索

    Returns:
        Tuple[str, List[Dict[str, Any]]]: (生成的回答, 检索结果列表)
    """
    # 根据是否提供图像选择检索方式
    if image is not None:
        # 图像检索：先对输入图像生成描述，再基于描述检索
        retrieved, _desc = await image_to_image_search(file=image, top_k=top_k)
    else:
        # 文本检索：直接基于用户问题检索
        retrieved = await text_to_image_search(query=query, top_k=top_k)

    # 获取多模态模型客户端
    mllm_client = get_mllm_client()

    # 准备图像数据：将检索到的图像转换为base64编码
    image_contents = []
    for idx, item in enumerate(retrieved, start=1):
        meta = item.get("metadata") or {}
        file_path = meta.get("file_path", "")
        if file_path and os.path.exists(file_path):
            try:
                image_b64 = _read_image_as_base64(file_path)
                image_contents.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_b64}",
                    }
                })
                # 添加文本描述，帮助模型理解图像顺序
                image_contents.append({
                    "type": "text",
                    "text": f"\n[图像 {idx}]"
                })
            except Exception as e:
                print(f"警告：无法读取图像文件 {file_path}: {e}")

    # 构建提示词，指导模型基于图像内容回答问题
    prompt = (
        "你是一个多模态知识库问答助手。你将看到若干张检索到的相关图像，"
        "以及用户提出的问题。请仔细观察这些图像的内容，基于图像中的视觉信息回答用户的问题。\n\n"
        f"用户问题：{query}\n\n"
        "请基于图像内容进行回答，可以自然地引用相关图像，例如“根据第一张图像，可以看到……”。"
        "如果图像信息不足以回答某些部分，请明确说明不确定。"
    )

    # 调用多模态模型生成回答
    if image_contents:
        # 构建完整的消息内容
        full_content = [{"type": "text", "text": prompt}]
        full_content.extend(image_contents)

        # 使用新的chat_with_images方法
        answer = await mllm_client.chat_with_images(content=full_content)
    else:
        answer = "未找到相关图像，无法回答问题。"
    # 返回回答和检索结果
    return answer, retrieved

