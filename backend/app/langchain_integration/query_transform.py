"""
查询重写 / Multi-Query 扩展模块

使用 LLM 将用户原始查询改写为检索友好表达，并生成多角度子查询以提升召回率。
"""
import logging
from typing import List, Optional

from app.core.config import settings
from app.core.memory_cache import TTLMemoryCache
from app.core.timing import get_current_timing_collector, timing_stage
from app.langchain_integration.models import MultimodalChatModel, get_task_text_chat_model

logger = logging.getLogger(__name__)

_REWRITE_CACHE_TTL_SECONDS = 30 * 60
_REWRITE_CACHE_MAX_SIZE = 512

REWRITE_SYSTEM_PROMPT = (
    "你是一个搜索查询优化专家。请将用户的查询改写为更适合向量检索的表达，"
    "保留核心语义，去除口语化表达，补充必要的上下文关键词。只输出改写后的查询，不要解释。"
)

EXPAND_SYSTEM_PROMPT = (
    "你是一个搜索查询扩展专家。请根据用户的查询，从不同角度生成 {n} 个语义相关但表达不同的子查询，"
    "用于提升检索召回率。每行输出一个子查询，不要编号，不要解释。"
)

_rewrite_cache: TTLMemoryCache[str, str] = TTLMemoryCache(
    ttl_seconds=_REWRITE_CACHE_TTL_SECONDS,
    max_size=_REWRITE_CACHE_MAX_SIZE,
)
_expand_cache: TTLMemoryCache[tuple[str, int], List[str]] = TTLMemoryCache(
    ttl_seconds=_REWRITE_CACHE_TTL_SECONDS,
    max_size=_REWRITE_CACHE_MAX_SIZE,
)


class QueryRewriter:
    """查询重写与 Multi-Query 扩展"""

    def __init__(self, chat_model: Optional[MultimodalChatModel] = None):
        if chat_model is None:
            task_model = get_task_text_chat_model()
            chat_model = MultimodalChatModel(
                base_url=task_model.base_url,
                api_key=task_model.api_key,
                model_name=task_model.model_name,
                temperature=0.3,
            )
        self.chat_model = chat_model

    async def rewrite(self, query: str) -> str:
        """将查询改写为检索友好表达"""
        from langchain_core.messages import SystemMessage, HumanMessage

        collector = get_current_timing_collector()
        cached = _rewrite_cache.get(query)
        if collector is not None:
            collector.set_metadata(rewrite_cache_hit=cached is not None)
        if cached is not None:
            return cached

        with timing_stage("query_rewrite", meta={"query_length": len(query)}):
            messages = [
                SystemMessage(content=REWRITE_SYSTEM_PROMPT),
                HumanMessage(content=query),
            ]
            result = await self.chat_model._agenerate(messages)
            rewritten = result.generations[0].message.content.strip()

        if rewritten:
            _rewrite_cache.set(query, rewritten)
        return rewritten

    async def expand(self, query: str, n: Optional[int] = None) -> List[str]:
        """
        生成 n 个不同角度的子查询，返回 [原始query] + [n个子查询]。
        """
        from langchain_core.messages import SystemMessage, HumanMessage

        n = n or settings.QUERY_MULTI_QUERY_COUNT
        cache_key = (query, n)
        collector = get_current_timing_collector()
        cached = _expand_cache.get(cache_key)
        if collector is not None:
            collector.set_metadata(expand_cache_hit=cached is not None)
        if cached is not None:
            return list(cached)

        system_prompt = EXPAND_SYSTEM_PROMPT.format(n=n)

        with timing_stage("query_expand", meta={"query_length": len(query), "expand_count": n}):
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

        expanded = [query] + sub_queries
        _expand_cache.set(cache_key, list(expanded))
        return expanded


# 全局实例缓存
_rewriter: Optional[QueryRewriter] = None


def get_query_rewriter() -> QueryRewriter:
    global _rewriter
    if _rewriter is None:
        _rewriter = QueryRewriter()
    return _rewriter


def reset_query_transform_caches() -> None:
    _rewrite_cache.clear()
    _expand_cache.clear()
