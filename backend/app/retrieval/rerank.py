"""
重排序模块

支持两种重排序策略：
1. CrossEncoder 精排（FlagEmbedding，默认）
2. simple_rerank 按 Chroma 距离排序（fallback）
"""
import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# 尝试加载 FlagEmbedding
_reranker = None
_reranker_load_attempted = False


def _get_reranker():
    """懒加载 FlagReranker 单例"""
    global _reranker, _reranker_load_attempted
    if _reranker_load_attempted:
        return _reranker
    _reranker_load_attempted = True
    try:
        from FlagEmbedding import FlagReranker
        model_name = settings.RERANK_MODEL_NAME
        logger.info(f"[Rerank] 加载 CrossEncoder 模型: {model_name}")
        _reranker = FlagReranker(model_name, use_fp16=True)
        logger.info("[Rerank] CrossEncoder 模型加载成功")
    except Exception as e:
        logger.warning(f"[Rerank] FlagEmbedding 不可用，降级为 simple_rerank: {e}")
        _reranker = None
    return _reranker


def simple_rerank(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """简单重排序（按 Chroma 距离从小到大排序）"""
    return sorted(results, key=lambda x: x.get("score", 0.0))


def cross_encoder_rerank(
    query: str,
    results: List[Dict[str, Any]],
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    使用 CrossEncoder 对候选结果精排。

    Args:
        query: 查询文本
        results: 候选结果列表，每个元素需包含 "document" 字段
        top_k: 返回数量，默认使用 RERANK_TOP_K 配置

    Returns:
        精排后的 top_k 结果
    """
    if not results:
        return results

    top_k = top_k or settings.RERANK_TOP_K
    reranker = _get_reranker()

    if reranker is None:
        logger.debug("[Rerank] 降级为 simple_rerank")
        return simple_rerank(results)[:top_k]

    # 构建 (query, doc) 对
    pairs = [[query, r.get("document", "")] for r in results]

    try:
        scores = reranker.compute_score(pairs)
        # compute_score 单条时返回 float，多条返回 list
        if isinstance(scores, (int, float)):
            scores = [scores]

        # 将分数写入结果并按分数降序排序
        for r, s in zip(results, scores):
            r["rerank_score"] = float(s)

        ranked = sorted(results, key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        logger.info(
            f"[Rerank] CrossEncoder 精排完成: {len(results)} 候选 → top-{top_k}"
        )
        return ranked[:top_k]

    except Exception as e:
        logger.warning(f"[Rerank] CrossEncoder 打分失败，降级: {e}")
        return simple_rerank(results)[:top_k]
