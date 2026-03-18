"""
No-RAG 基线：不检索任何知识库，直接将问题发给 MLLM 生成答案。

用途：作为生成器评估的下界对照，证明检索对生成质量有帮助。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.langchain_integration.models import get_chat_model  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402

_PROMPT = (
    "你是一个多模态知识库问答助手。请根据以下问题直接作答，"
    "如果你不确定，请明确说明。\n\n"
    "用户问题：{query}"
)


async def generate(query: str) -> Dict[str, Any]:
    """
    不检索，直接用 MLLM 回答问题。

    Returns:
        dict: {
            "generated_answer": str,
            "context": "",        # 无检索上下文
            "images": [],         # 无图片
        }
    """
    model = get_chat_model()
    messages = [HumanMessage(content=_PROMPT.format(query=query))]
    result = await model._agenerate(messages)
    return {
        "generated_answer": result.generations[0].message.content,
        "context": "",
        "images": [],
    }
