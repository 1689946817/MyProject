"""
Agentic RAG 模块（基于 LangGraph）

实现三种 Agentic 模式：
1. 查询路由：判断查询类型，选择检索策略
2. CRAG（Corrective RAG）：检索后评估相关性，必要时重新检索或 Web 搜索
3. Self-RAG：生成后自我评估，决定是否需要更多检索
"""
import json
import logging
import re
from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from app.core.config import settings
from app.core.timing import get_current_timing_collector, timing_stage
from app.langchain_integration.models import get_primary_text_chat_model, get_task_text_chat_model

logger = logging.getLogger(__name__)
get_chat_model = get_primary_text_chat_model


class IntentClassification(TypedDict):
    """聊天意图分类结果。"""

    presentation_mode: Literal["direct_answer", "rag_answer", "image_only", "image_plus_answer"]
    execution_mode: Literal[
        "direct_llm",
        "multimodal_rag",
        "image_similarity",
        "image_grounded_answer",
        "uploaded_image_qa",
        "save_uploaded_image",
    ]
    use_rag: bool
    has_uploaded_image: bool
    wants_images: bool
    confidence: float
    reason: str


class AgenticRAGState(TypedDict):
    """Agentic RAG 状态"""
    query: str
    chat_history: List[tuple]
    top_k: int
    enable_score_filter: bool
    min_relevance_score: Optional[float]
    documents: List[Dict[str, Any]]
    text_chunks: List[Any]
    answer: str
    retrieval_attempt: int
    relevance_score: float
    needs_retry: bool
    retrieval_meta: Dict[str, Any]


_DIRECT_ANSWER = "direct_answer"
_RAG_ANSWER = "rag_answer"
_IMAGE_ONLY = "image_only"
_IMAGE_PLUS_ANSWER = "image_plus_answer"

_COMMON_FACT_PATTERNS = [
    "长城",
    "首都",
    "中国哪个城市",
    "是什么国家",
    "谁发明",
    "位于哪里",
    "在哪个国家",
]
_PRODUCT_VENDOR_HINTS = [
    "华为",
    "huawei",
    "思科",
    "cisco",
    "h3c",
    "新华三",
    "锐捷",
    "ruijie",
    "juniper",
    "瞻博",
    "路由器",
    "交换机",
    "防火墙",
    "网关",
    "netengine",
]
_PRODUCT_DOC_HINTS = [
    "技术规格",
    "规格",
    "参数",
    "配置",
    "功能特性",
    "特性",
    "型号",
    "系列",
]
_TABULAR_DOC_HINTS = [
    "对照表",
    "表格",
    "列表",
    "比较",
    "对比",
]
_INTERNAL_KNOWLEDGE_HINTS = [
    "公司",
    "内部",
    "制度",
    "流程",
    "审批",
    "报销",
    "工资",
    "薪资",
    "发放",
    "离职",
    "入职",
    "社保",
    "裁员",
    "员工",
    "知识库",
]
_IMAGE_LOOKUP_HINTS = [
    "图片",
    "图像",
    "配图",
    "海报",
    "流程图",
    "示意图",
    "相似",
    "类似",
    "找一张",
    "找个",
]
_SAVE_IMAGE_HINTS = [
    "存一下",
    "保存",
    "存入",
    "存到",
    "加入知识库",
    "加入图片知识库",
    "放到知识库",
    "收录到知识库",
]
_ANSWER_HINTS = [
    "什么",
    "怎么",
    "如何",
    "为什么",
    "告诉我",
    "解释",
    "说明",
    "讲了什么",
    "内容",
    "第",
    "步骤",
]


def _has_model_pattern(normalized: str) -> bool:
    return bool(re.search(r"(?=.*[a-z])(?=.*\d)[a-z\d-]{4,}", normalized))


def _has_product_doc_intent(normalized: str) -> bool:
    has_doc_hint = any(token in normalized for token in _PRODUCT_DOC_HINTS)
    has_tabular_hint = any(token in normalized for token in _TABULAR_DOC_HINTS)
    has_vendor_or_product = any(token in normalized for token in _PRODUCT_VENDOR_HINTS)
    has_model_pattern = _has_model_pattern(normalized)
    return (has_model_pattern and (has_doc_hint or has_tabular_hint)) or (
        has_vendor_or_product and has_doc_hint
    )


def _default_intent(
    *,
    presentation_mode: Literal["direct_answer", "rag_answer", "image_only", "image_plus_answer"],
    execution_mode: Literal[
        "direct_llm",
        "multimodal_rag",
        "image_similarity",
        "image_grounded_answer",
        "uploaded_image_qa",
        "save_uploaded_image",
    ],
    use_rag: bool,
    has_uploaded_image: bool,
    wants_images: bool,
    confidence: float,
    reason: str,
) -> IntentClassification:
    return {
        "presentation_mode": presentation_mode,
        "execution_mode": execution_mode,
        "use_rag": use_rag,
        "has_uploaded_image": has_uploaded_image,
        "wants_images": wants_images,
        "confidence": confidence,
        "reason": reason,
    }


def _rule_based_intent(query: str, has_uploaded_image: bool) -> Optional[IntentClassification]:
    normalized = re.sub(r"\s+", "", query or "").lower()
    has_model_pattern = _has_model_pattern(normalized)
    has_product_doc_intent = _has_product_doc_intent(normalized)
    wants_images = any(token in normalized for token in _IMAGE_LOOKUP_HINTS)
    asks_answer = any(token in normalized for token in _ANSWER_HINTS)
    asks_similarity = any(token in normalized for token in ["相似", "类似"])
    asks_find = any(token in normalized for token in ["找", "搜索", "给我", "帮我找"])
    asks_save = any(token in normalized for token in _SAVE_IMAGE_HINTS)
    references_uploaded_image = any(token in normalized for token in ["这张图片", "这张图", "图里", "图片里", "图上", "图片上"])
    internal_knowledge = any(token in normalized for token in _INTERNAL_KNOWLEDGE_HINTS)
    common_fact = any(token in normalized for token in _COMMON_FACT_PATTERNS)
    explicit_explanation_request = any(
        token in normalized for token in ["告诉我", "并告诉我", "并说明", "解释", "回答", "分析", "讲讲", "说说"]
    )

    if has_uploaded_image and asks_save and not (asks_similarity or asks_find or asks_answer):
        return _default_intent(
            presentation_mode=_DIRECT_ANSWER,
            execution_mode="save_uploaded_image",
            use_rag=False,
            has_uploaded_image=True,
            wants_images=False,
            confidence=0.97,
            reason="save_uploaded_image",
        )

    if has_uploaded_image and asks_similarity and wants_images and not asks_answer:
        return _default_intent(
            presentation_mode=_IMAGE_ONLY,
            execution_mode="image_similarity",
            use_rag=False,
            has_uploaded_image=True,
            wants_images=True,
            confidence=0.96,
            reason="uploaded_image_similarity_lookup",
        )

    if has_uploaded_image and references_uploaded_image and not (asks_similarity or asks_find):
        return _default_intent(
            presentation_mode=_DIRECT_ANSWER,
            execution_mode="uploaded_image_qa",
            use_rag=False,
            has_uploaded_image=True,
            wants_images=False,
            confidence=0.94,
            reason="uploaded_image_content_question",
        )

    if has_uploaded_image and wants_images and asks_answer:
        return _default_intent(
            presentation_mode=_IMAGE_PLUS_ANSWER,
            execution_mode="image_grounded_answer",
            use_rag=True,
            has_uploaded_image=True,
            wants_images=True,
            confidence=0.93,
            reason="uploaded_image_similarity_plus_answer",
        )

    if has_uploaded_image and not wants_images:
        return _default_intent(
            presentation_mode=_DIRECT_ANSWER,
            execution_mode="uploaded_image_qa",
            use_rag=False,
            has_uploaded_image=True,
            wants_images=False,
            confidence=0.9,
            reason="uploaded_image_only",
        )

    if wants_images and asks_answer and explicit_explanation_request:
        return _default_intent(
            presentation_mode=_IMAGE_PLUS_ANSWER,
            execution_mode="image_grounded_answer",
            use_rag=True,
            has_uploaded_image=False,
            wants_images=True,
            confidence=0.87,
            reason="image_lookup_plus_answer",
        )

    if wants_images and (asks_find or asks_similarity):
        return _default_intent(
            presentation_mode=_IMAGE_ONLY,
            execution_mode="image_similarity",
            use_rag=False,
            has_uploaded_image=False,
            wants_images=True,
            confidence=0.9,
            reason="image_lookup",
        )

    if has_product_doc_intent:
        return _default_intent(
            presentation_mode=_RAG_ANSWER,
            execution_mode="multimodal_rag",
            use_rag=True,
            has_uploaded_image=False,
            wants_images=False,
            confidence=0.92,
            reason="product_spec_lookup",
        )

    if internal_knowledge:
        return _default_intent(
            presentation_mode=_RAG_ANSWER,
            execution_mode="multimodal_rag",
            use_rag=True,
            has_uploaded_image=False,
            wants_images=False,
            confidence=0.86,
            reason="internal_knowledge",
        )

    if common_fact and not has_model_pattern and not has_product_doc_intent:
        return _default_intent(
            presentation_mode=_DIRECT_ANSWER,
            execution_mode="direct_llm",
            use_rag=False,
            has_uploaded_image=False,
            wants_images=False,
            confidence=0.88,
            reason="common_fact",
        )

    return None


def _coerce_classifier_output(payload: Dict[str, Any], has_uploaded_image: bool) -> Optional[IntentClassification]:
    try:
        presentation_mode = str(payload.get("presentation_mode", "")).strip()
        execution_mode = str(payload.get("execution_mode", "")).strip()
        if presentation_mode not in {_DIRECT_ANSWER, _RAG_ANSWER, _IMAGE_ONLY, _IMAGE_PLUS_ANSWER}:
            return None
        if execution_mode not in {
            "direct_llm",
            "multimodal_rag",
            "image_similarity",
            "image_grounded_answer",
            "uploaded_image_qa",
            "save_uploaded_image",
        }:
            return None
        return _default_intent(
            presentation_mode=presentation_mode,
            execution_mode=execution_mode,
            use_rag=bool(payload.get("use_rag", execution_mode in {"multimodal_rag", "image_grounded_answer"})),
            has_uploaded_image=has_uploaded_image,
            wants_images=bool(payload.get("wants_images", presentation_mode in {_IMAGE_ONLY, _IMAGE_PLUS_ANSWER})),
            confidence=max(0.0, min(float(payload.get("confidence", 0.5)), 1.0)),
            reason=str(payload.get("reason", "llm_classifier")),
        )
    except (TypeError, ValueError):
        return None


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fenced:
        text = fenced.group(1)
    else:
        brace = re.search(r"(\{.*\})", text, flags=re.S)
        if brace:
            text = brace.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


async def classify_chat_intent(
    query: str,
    has_uploaded_image: bool = False,
    chat_model=None,
) -> IntentClassification:
    """两层输出的聊天意图分类。"""
    with timing_stage("intent_classification", meta={"has_uploaded_image": has_uploaded_image}):
        rule_intent = _rule_based_intent(query, has_uploaded_image)
        if rule_intent is not None:
            collector = get_current_timing_collector()
            if collector is not None:
                collector.set_metadata(
                    execution_mode=rule_intent["execution_mode"],
                    presentation_mode=rule_intent["presentation_mode"],
                )
            return rule_intent

        model = chat_model or get_task_text_chat_model()
        prompt = f"""你是一个聊天路由分类器。请根据用户问题判断回答方式，并只返回 JSON。

返回字段：
- presentation_mode: direct_answer | rag_answer | image_only | image_plus_answer
- execution_mode: direct_llm | multimodal_rag | image_similarity | image_grounded_answer | uploaded_image_qa
 - execution_mode: direct_llm | multimodal_rag | image_similarity | image_grounded_answer | uploaded_image_qa | save_uploaded_image
- use_rag: boolean
- wants_images: boolean
- confidence: 0 到 1
- reason: 简短英文标识

决策规则：
1. 通识、常识、公开事实，优先 direct_llm。
2. 需要公司内部知识、制度、流程、审批、工资、员工政策等支撑的，一律 multimodal_rag。
3. 纯找图、找类似图，只返回图片时，走 image_similarity。
4. 既要图片又要解释、要基于找到的图片回答时，走 image_grounded_answer。
5. 用户上传了图片，且只是在问上传图本身内容时，走 uploaded_image_qa。
6. 用户上传了图片，且明确要求保存到知识库时，走 save_uploaded_image。
7. 不确定时，优先进入检索增强路线，而不是 direct_llm。

用户是否上传图片：{str(has_uploaded_image).lower()}
用户问题：{query}
"""
        try:
            result = await model._agenerate([HumanMessage(content=prompt)])
            raw = result.generations[0].message.content
            parsed = _extract_json_object(raw)
            if isinstance(parsed, dict):
                intent = _coerce_classifier_output(parsed, has_uploaded_image)
                if intent is not None:
                    collector = get_current_timing_collector()
                    if collector is not None:
                        collector.set_metadata(
                            execution_mode=intent["execution_mode"],
                            presentation_mode=intent["presentation_mode"],
                        )
                    return intent
        except Exception as exc:  # pragma: no cover - network/model failures are best-effort fallback
            logger.warning("[IntentClassifier] LLM classifier failed, fallback to conservative routing: %s", exc)

        intent = _default_intent(
            presentation_mode=_RAG_ANSWER,
            execution_mode="multimodal_rag",
            use_rag=True,
            has_uploaded_image=has_uploaded_image,
            wants_images=has_uploaded_image,
            confidence=0.35,
            reason="fallback_to_retrieval",
        )
        collector = get_current_timing_collector()
        if collector is not None:
            collector.set_metadata(
                execution_mode=intent["execution_mode"],
                presentation_mode=intent["presentation_mode"],
            )
        return intent


async def retrieve_documents(
    state: AgenticRAGState,
    *,
    retriever=None,
    doc_vector_store=None,
    text_top_k: int = 5,
) -> AgenticRAGState:
    """执行首次检索，复用现有图片来源检索与文档文本块检索。"""
    if retriever is None:
        from app.langchain_integration.retrievers import get_multimodal_retriever

        retriever = get_multimodal_retriever()
    if doc_vector_store is None:
        from app.langchain_integration.vectorstores import get_document_vector_store

        doc_vector_store = get_document_vector_store()

    query = state["query"]
    top_k = int(state.get("top_k", 5) or 5)
    attempt = int(state.get("retrieval_attempt", 1) or 1)
    enable_score_filter = bool(state.get("enable_score_filter", False))
    min_relevance_score = state.get("min_relevance_score")
    stage_name = "agentic_retrieve_initial" if attempt <= 1 else "agentic_retrieve_retry"

    with timing_stage(
        stage_name,
        meta={
            "attempt": attempt,
            "top_k": top_k,
            "enable_score_filter": enable_score_filter,
            "retry": attempt > 1,
        },
    ):
        documents = await retriever.async_search_with_dict_output(
            query,
            top_k=top_k,
            fast=False,
            enable_score_filter=enable_score_filter,
            min_relevance_score=min_relevance_score,
        )
        text_chunks = doc_vector_store.similarity_search(query, k=text_top_k)

    state["documents"] = documents
    state["text_chunks"] = text_chunks
    state["retrieval_meta"] = {
        **dict(state.get("retrieval_meta", {})),
        "document_count": len(documents),
        "text_chunk_count": len(text_chunks),
        "last_retrieval_attempt": attempt,
    }
    logger.info("[AgenticGraph] attempt=%s retrieved %s docs", attempt, len(documents))
    return state


async def retry_retrieve_documents(
    state: AgenticRAGState,
    *,
    retriever=None,
    doc_vector_store=None,
    text_top_k: int = 5,
) -> AgenticRAGState:
    """执行一次固定策略的重试检索。"""
    state["retrieval_attempt"] = 2
    return await retrieve_documents(
        state,
        retriever=retriever,
        doc_vector_store=doc_vector_store,
        text_top_k=text_top_k,
    )


async def grade_documents(state: AgenticRAGState) -> AgenticRAGState:
    """评估检索结果质量，决定是否需要单次 retry。"""
    documents = state["documents"]

    with timing_stage("agentic_grade", meta={"document_count": len(documents)}):
        top_documents = documents[: min(3, len(documents))]
        rerank_scores = [
            float(doc["rerank_score"])
            for doc in top_documents
            if isinstance(doc, dict) and doc.get("rerank_score") is not None
        ]
        if rerank_scores:
            relevance_score = sum(rerank_scores) / len(rerank_scores)
        else:
            rrf_scores = [
                float(doc["rrf_score"])
                for doc in top_documents
                if isinstance(doc, dict) and doc.get("rrf_score") is not None
            ]
            relevance_score = (sum(rrf_scores) / len(rrf_scores)) if rrf_scores else 0.0

        has_rerank_score = bool(rerank_scores)
        top_source_ids = [
            str(doc.get("id") or (doc.get("metadata") or {}).get("id"))
            for doc in top_documents
            if isinstance(doc, dict)
        ]
        asset_types = sorted(
            {
                str((doc.get("metadata") or {}).get("asset_type") or "image")
                for doc in documents
                if isinstance(doc, dict)
            }
        )
        retrieval_attempt = int(state.get("retrieval_attempt", 1) or 1)

        state["relevance_score"] = relevance_score
        state["needs_retry"] = len(documents) == 0 or (
            has_rerank_score and relevance_score < 0.35 and retrieval_attempt < 2
        )
        state["retrieval_meta"] = {
            **dict(state.get("retrieval_meta", {})),
            "document_count": len(documents),
            "has_rerank_score": has_rerank_score,
            "top_source_ids": top_source_ids,
            "asset_types": asset_types,
        }

    logger.info(
        "[AgenticGraph] grade score=%.3f retry=%s docs=%s",
        state["relevance_score"],
        state["needs_retry"],
        len(documents),
    )
    return state


def decide_next_after_grade(state: AgenticRAGState) -> Literal["retry", "generate"]:
    """根据评分结果决定是否做一次 retry。"""
    if state.get("needs_retry"):
        return "retry"
    return "generate"


async def generate_answer(state: AgenticRAGState, *, rag_chain=None) -> AgenticRAGState:
    """复用现有 RAGChain.agenerate_from_context 生成答案。"""
    if rag_chain is None:
        from app.langchain_integration.chains import get_rag_chain

        rag_chain = get_rag_chain()

    with timing_stage(
        "agentic_generate",
        meta={
            "document_count": len(state.get("documents", [])),
            "text_chunk_count": len(state.get("text_chunks", [])),
        },
    ):
        answer = await rag_chain.agenerate_from_context(
            query=state["query"],
            documents=state.get("documents", []),
            text_chunks=state.get("text_chunks", []),
            chat_history=state.get("chat_history", []),
        )

    state["answer"] = answer
    logger.info("[AgenticGraph] generated answer with %s docs", len(state.get("documents", [])))
    return state


def build_agentic_rag_graph(*, retriever=None, doc_vector_store=None, rag_chain=None):
    """构建最小可用的 Agentic RAG 图。"""
    text_top_k = int(getattr(rag_chain, "text_top_k", 5) or 5) if rag_chain is not None else 5
    workflow = StateGraph(AgenticRAGState)

    async def _retrieve_node(state: AgenticRAGState) -> AgenticRAGState:
        return await retrieve_documents(
            state,
            retriever=retriever,
            doc_vector_store=doc_vector_store,
            text_top_k=text_top_k,
        )

    async def _retry_retrieve_node(state: AgenticRAGState) -> AgenticRAGState:
        return await retry_retrieve_documents(
            state,
            retriever=retriever,
            doc_vector_store=doc_vector_store,
            text_top_k=text_top_k,
        )

    async def _generate_node(state: AgenticRAGState) -> AgenticRAGState:
        return await generate_answer(state, rag_chain=rag_chain)

    workflow.add_node("retrieve", _retrieve_node)
    workflow.add_node("grade", grade_documents)
    workflow.add_node("retry_retrieve", _retry_retrieve_node)
    workflow.add_node("generate", _generate_node)

    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "grade")
    workflow.add_conditional_edges(
        "grade",
        decide_next_after_grade,
        {
            "retry": "retry_retrieve",
            "generate": "generate",
        },
    )
    workflow.add_edge("retry_retrieve", "grade")
    workflow.add_edge("generate", END)
    return workflow.compile()


_agentic_graph = None


def get_agentic_rag_graph(*, retriever=None, doc_vector_store=None, rag_chain=None):
    """获取 Agentic RAG 图实例；显式传入依赖时返回隔离图实例。"""
    if retriever is not None or doc_vector_store is not None or rag_chain is not None:
        return build_agentic_rag_graph(
            retriever=retriever,
            doc_vector_store=doc_vector_store,
            rag_chain=rag_chain,
        )

    global _agentic_graph
    if _agentic_graph is None:
        _agentic_graph = build_agentic_rag_graph()
    return _agentic_graph


def _build_agentic_retrieval_steps(
    *,
    query: str,
    top_k: int,
    execution_mode: str,
    presentation_mode: str,
    classifier_reason: str,
    has_uploaded_image: bool,
    documents: List[Dict[str, Any]],
    final_state: AgenticRAGState,
) -> List[Dict[str, Any]]:
    retrieval_meta = dict(final_state.get("retrieval_meta", {}))
    relevance_score = float(final_state.get("relevance_score", 0.0) or 0.0)
    steps: List[Dict[str, Any]] = [
        {
            "key": "intent",
            "label": "意图",
            "summary": f"{execution_mode} / {presentation_mode}",
            "details": {
                "execution_mode": execution_mode,
                "presentation_mode": presentation_mode,
                "use_rag": True,
                "has_uploaded_image": has_uploaded_image,
                "reason": classifier_reason,
            },
        },
        {
            "key": "query",
            "label": "查询",
            "summary": query[:120],
            "details": {"query": query, "top_k": top_k},
        },
        {
            "key": "retrieve",
            "label": "首次检索",
            "summary": f"召回 {len(documents)} 条结果",
            "details": {
                "count": len(documents),
                "attempt": 1,
                "top_source_ids": retrieval_meta.get("top_source_ids", []),
                "asset_types": retrieval_meta.get("asset_types", []),
            },
        },
        {
            "key": "grade",
            "label": "评分",
            "summary": f"相关性 {relevance_score:.3f}",
            "details": {
                "relevance_score": round(relevance_score, 6),
                "document_count": retrieval_meta.get("document_count", len(documents)),
                "has_rerank_score": bool(retrieval_meta.get("has_rerank_score", False)),
            },
        },
    ]

    if int(final_state.get("retrieval_attempt", 1) or 1) > 1:
        steps.append(
            {
                "key": "retry",
                "label": "重试检索",
                "summary": "首次检索质量不足，已执行一次重试",
                "details": {
                    "attempt": int(final_state.get("retrieval_attempt", 1) or 1),
                    "top_source_ids": retrieval_meta.get("top_source_ids", []),
                    "asset_types": retrieval_meta.get("asset_types", []),
                },
            }
        )

    steps.append(
        {
            "key": "generate",
            "label": "生成",
            "summary": "已基于检索上下文生成回答",
            "details": {
                "document_count": len(documents),
                "text_chunk_count": retrieval_meta.get("text_chunk_count", len(final_state.get("text_chunks", []))),
            },
        }
    )
    return steps


async def run_agentic_multimodal_rag(
    *,
    query: str,
    top_k: int,
    chat_history: Optional[List[Tuple[str, str]]],
    enable_score_filter: bool,
    min_relevance_score: Optional[float],
    rag_chain,
    retriever,
    doc_vector_store,
    execution_mode: str,
    presentation_mode: str,
    classifier_reason: str,
    has_uploaded_image: bool,
) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """运行最小 LangGraph 主链路，并返回兼容现有 adapter 的结果。"""
    initial_state: AgenticRAGState = {
        "query": query,
        "chat_history": chat_history or [],
        "top_k": top_k,
        "enable_score_filter": enable_score_filter,
        "min_relevance_score": min_relevance_score,
        "documents": [],
        "text_chunks": [],
        "answer": "",
        "retrieval_attempt": 1,
        "relevance_score": 0.0,
        "needs_retry": False,
        "retrieval_meta": {},
    }

    with timing_stage("agentic_graph_total", meta={"top_k": top_k, "execution_mode": execution_mode}):
        graph = get_agentic_rag_graph(
            retriever=retriever,
            doc_vector_store=doc_vector_store,
            rag_chain=rag_chain,
        )
        final_state = await graph.ainvoke(initial_state)

    collector = get_current_timing_collector()
    if collector is not None:
        collector.set_metadata(
            agentic_graph_enabled=True,
            agentic_retry_used=bool(int(final_state.get("retrieval_attempt", 1) or 1) > 1),
            agentic_relevance_score=final_state.get("relevance_score"),
        )

    documents = list(final_state.get("documents", []))
    retrieval_steps = _build_agentic_retrieval_steps(
        query=query,
        top_k=top_k,
        execution_mode=execution_mode,
        presentation_mode=presentation_mode,
        classifier_reason=classifier_reason,
        has_uploaded_image=has_uploaded_image,
        documents=documents,
        final_state=final_state,
    )
    return final_state.get("answer", ""), documents, retrieval_steps
