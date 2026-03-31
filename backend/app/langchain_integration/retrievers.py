"""
LangChain 检索器集成模块

P0 升级后的检索流程：
  原始 query
    → QueryRewriter.expand() 生成多个子查询
    → 每个子查询执行混合检索（向量 + BM25，RRF 融合）
    → 多查询结果按 doc_id 去重合并（取最高分）
    → top-N 候选送入 CrossEncoder 精排
    → 返回 top-K
"""
import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import UploadFile
from langchain_core.documents import Document

from app.core.config import settings
from app.langchain_integration.models import get_chat_model, MultimodalChatModel
from app.langchain_integration.vectorstores import ChromaVectorStore, get_vector_store
from app.retrieval.rerank import cross_encoder_rerank, simple_rerank
from app.semantic.prompts import IMAGE_DESCRIPTION_PROMPT

logger = logging.getLogger(__name__)


def _hybrid_search_sync(
    query: str,
    vector_store: ChromaVectorStore,
    candidate_k: int,
) -> List[Dict[str, Any]]:
    """
    同步混合检索（向量 + BM25 + RRF 融合）。
    BM25 索引未就绪时退化为纯向量检索。
    """
    from app.retrieval.hybrid import get_bm25_index, reciprocal_rank_fusion

    vector_hits = vector_store.search_by_text(query, top_k=candidate_k)

    bm25_index = get_bm25_index()
    if bm25_index.is_ready:
        bm25_hits = bm25_index.search(query, top_k=candidate_k)
        id_to_doc = {h["id"]: h.get("document", "") for h in vector_hits}
        for hit in bm25_hits:
            if "document" not in hit:
                hit["document"] = id_to_doc.get(hit["id"], "")
        return reciprocal_rank_fusion(vector_hits, bm25_hits)

    logger.debug("[Retriever] BM25 索引未就绪，使用纯向量检索")
    return vector_hits


async def _multi_query_hybrid_search(
    query: str,
    vector_store: ChromaVectorStore,
    candidate_k: int,
) -> List[Dict[str, Any]]:
    """
    Multi-Query + 混合检索：
    1. 如果启用查询重写，扩展为多个子查询
    2. 每个子查询独立执行混合检索
    3. 按 doc_id 去重合并（取最高分）
    """
    if settings.QUERY_REWRITE_ENABLED:
        try:
            from app.langchain_integration.query_transform import get_query_rewriter
            rewriter = get_query_rewriter()
            queries = await rewriter.expand(query)
        except Exception as e:
            logger.warning(f"[Retriever] 查询扩展失败，使用原始查询: {e}")
            queries = [query]
    else:
        queries = [query]

    all_results: Dict[str, Dict[str, Any]] = {}

    # 并行执行各子查询的混合检索
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, _hybrid_search_sync, q, vector_store, candidate_k)
        for q in queries
    ]
    all_hits = await asyncio.gather(*tasks)

    for hits in all_hits:
        for hit in hits:
            doc_id = hit["id"]
            new_score = hit.get("rrf_score", hit.get("score", 0.0))
            existing_score = all_results.get(doc_id, {}).get("rrf_score", -1)
            if doc_id not in all_results or new_score > existing_score:
                hit["rrf_score"] = new_score
                all_results[doc_id] = hit

    merged = sorted(
        all_results.values(),
        key=lambda x: x.get("rrf_score", x.get("score", 0.0)),
        reverse=True,
    )

    logger.info(
        f"[Retriever] Multi-Query 合并: {len(queries)} 个查询 → {len(merged)} 个去重结果"
    )
    return merged


class MultimodalRetriever:
    """
    多模态检索器（P0 升级版）

    支持：
    - 文本到图像检索（Multi-Query + 混合检索 + CrossEncoder 精排）
    - 图像到图像检索（通过生成描述）
    """

    def __init__(
        self,
        vector_store: Optional[ChromaVectorStore] = None,
        chat_model: Optional[MultimodalChatModel] = None,
        top_k: int = 10,
    ):
        self.vector_store = vector_store or get_vector_store()
        self.chat_model = chat_model or get_chat_model()
        self.top_k = top_k

    async def text_to_image_search(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[Document]:
        """
        文本到图像检索（完整 P0 流程）

        query → Multi-Query 扩展 → 混合检索(向量+BM25) → RRF 融合 → CrossEncoder 精排 → top-K
        """
        k = top_k or self.top_k
        candidate_k = settings.RERANK_CANDIDATE_K

        candidates = await _multi_query_hybrid_search(
            query, self.vector_store, candidate_k
        )

        reranked = cross_encoder_rerank(query, candidates, top_k=k)

        documents = []
        for hit in reranked:
            doc = Document(
                page_content=hit.get("document", ""),
                metadata=hit.get("metadata", {}),
            )
            doc.metadata["score"] = hit.get(
                "rerank_score", hit.get("rrf_score", hit.get("score", 0.0))
            )
            documents.append(doc)

        return documents

    async def image_to_image_search(
        self,
        file: UploadFile,
        top_k: Optional[int] = None,
    ) -> Tuple[List[Document], str]:
        """图像到图像检索：先生成描述，再走文本检索路径。"""
        k = top_k or self.top_k

        contents = await file.read()
        b64_image = base64.b64encode(contents).decode("utf-8")

        description = await self.chat_model.agenerate_description(
            image_b64=b64_image,
            prompt=IMAGE_DESCRIPTION_PROMPT,
        )

        documents = await self.text_to_image_search(description, top_k=k)
        return documents, description

    def search_with_dict_output(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        同步检索并返回字典格式结果（兼容旧接口）。

        同步方法无法使用 Multi-Query（需要 async LLM 调用），
        此处使用混合检索 + CrossEncoder 精排。
        """
        k = top_k or self.top_k
        candidate_k = settings.RERANK_CANDIDATE_K

        candidates = _hybrid_search_sync(query, self.vector_store, candidate_k)
        return cross_encoder_rerank(query, candidates, top_k=k)

    async def async_search_with_dict_output(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        异步检索并返回字典格式结果（完整 P0 管线：Multi-Query + 混合检索 + 精排）。
        """
        k = top_k or self.top_k
        candidate_k = settings.RERANK_CANDIDATE_K

        candidates = await _multi_query_hybrid_search(
            query, self.vector_store, candidate_k
        )
        return cross_encoder_rerank(query, candidates, top_k=k)


# 全局检索器实例缓存
_retriever: Optional[MultimodalRetriever] = None


def get_multimodal_retriever(top_k: int = 10) -> MultimodalRetriever:
    """获取多模态检索器实例（单例模式）"""
    global _retriever
    if _retriever is None:
        _retriever = MultimodalRetriever(top_k=top_k)
    return _retriever
