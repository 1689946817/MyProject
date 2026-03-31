"""
查询重写 / Multi-Query 扩展模块

使用 LLM 将用户原始查询改写为检索友好表达，并生成多角度子查询以提升召回率。
"""
import logging
from typing import List, Optional

from app.core.config import settings
from app.langchain_integration.models import MultimodalChatModel

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = (
    "你是一个搜索查询优化专家。请将用户的查询改写为更适合向量检索的表达，"
    "保留核心语义，去除口语化表达，补充必要的上下文关键词。只输出改写后的查询，不要解释。"
)

EXPAND_SYSTEM_PROMPT = (
    "你是一个搜索查询扩展专家。请根据用户的查询，从不同角度生成 {n} 个语义相关但表达不同的子查询，"
    "用于提升检索召回率。每行输出一个子查询，不要编号，不要解释。"
)


class QueryRewriter:
    """查询重写与 Multi-Query 扩展"""

    def __init__(self, chat_model: Optional[MultimodalChatModel] = None):
        if chat_model is None:
            # 使用 LLM 配置（文本生成模型）而非 MLLM
            chat_model = MultimodalChatModel(
                base_url=settings.LLM_BASE_URL,
                api_key=settings.LLM_API_KEY,
                model_name=settings.LLM_MODEL_NAME,
                temperature=0.3,
            )
        self.chat_model = chat_model

    async def rewrite(self, query: str) -> str:
        """将查询改写为检索友好表达"""
        from langchain_core.messages import SystemMessage, HumanMessage

        messages = [
            SystemMessage(content=REWRITE_SYSTEM_PROMPT),
            HumanMessage(content=query),
        ]
        result = await self.chat_model._agenerate(messages)
        return result.generations[0].message.content.strip()

    async def expand(self, query: str, n: Optional[int] = None) -> List[str]:
        """
        生成 n 个不同角度的子查询，返回 [原始query] + [n个子查询]。
        """
        from langchain_core.messages import SystemMessage, HumanMessage

        n = n or settings.QUERY_MULTI_QUERY_COUNT
        system_prompt = EXPAND_SYSTEM_PROMPT.format(n=n)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query),
        ]
        result = await self.chat_model._agenerate(messages)
        raw = result.generations[0].message.content.strip()

        sub_queries = [line.strip() for line in raw.splitlines() if line.strip()]
        # 截取前 n 个
        sub_queries = sub_queries[:n]

        logger.info(f"[QueryRewriter] 原始查询: {query}")
        logger.info(f"[QueryRewriter] 扩展子查询: {sub_queries}")

        return [query] + sub_queries


# 全局实例缓存
_rewriter: Optional[QueryRewriter] = None


def get_query_rewriter() -> QueryRewriter:
    global _rewriter
    if _rewriter is None:
        _rewriter = QueryRewriter()
    return _rewriter
