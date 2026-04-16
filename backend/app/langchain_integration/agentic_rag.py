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
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph

from app.core.config import settings
from app.core.timing import get_current_timing_collector, timing_stage
from app.langchain_integration.models import get_primary_text_chat_model, get_task_text_chat_model

logger = logging.getLogger(__name__)


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
    documents: List[Dict[str, Any]]
    answer: str
    route: str  # "vectorstore" | "web_search"
    relevance_score: float  # 0-1
    needs_retry: bool
    intent: Optional[IntentClassification]


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


async def route_query(state: AgenticRAGState) -> AgenticRAGState:
    """查询路由：判断是否需要检索知识库"""
    query = state["query"]

    # 简单规则：包含"最新"、"今天"等时间词 → web_search
    if any(kw in query for kw in ["最新", "今天", "昨天", "新闻"]):
        state["route"] = "web_search"
        logger.info(f"[Route] 查询路由到 web_search: {query}")
    else:
        state["route"] = "vectorstore"
        logger.info(f"[Route] 查询路由到 vectorstore: {query}")

    return state


async def retrieve_documents(state: AgenticRAGState) -> AgenticRAGState:
    """从向量库检索文档"""
    from app.langchain_integration.retrievers import get_multimodal_retriever

    query = state["query"]
    retriever = get_multimodal_retriever()

    # 使用完整检索管线
    docs = await retriever.async_search_with_dict_output(query, top_k=5)
    state["documents"] = docs

    logger.info(f"[Retrieve] 检索到 {len(docs)} 篇文档")
    return state


async def grade_documents(state: AgenticRAGState) -> AgenticRAGState:
    """CRAG：评估检索文档的相关性"""
    query = state["query"]
    documents = state["documents"]

    if not documents:
        state["relevance_score"] = 0.0
        return state

    # 简化版：用 rerank_score 作为相关性
    avg_score = sum(d.get("rerank_score", d.get("rrf_score", 0.5)) for d in documents) / len(documents)
    state["relevance_score"] = avg_score

    logger.info(f"[Grade] 文档相关性评分: {avg_score:.2f}")
    return state


async def decide_next(state: AgenticRAGState) -> Literal["generate", "web_search"]:
    """决策：相关性低则转 web_search，否则生成"""
    if state["relevance_score"] < 0.3:
        logger.info("[Decide] 相关性过低，转 web_search")
        return "web_search"
    return "generate"


async def web_search_fallback(state: AgenticRAGState) -> AgenticRAGState:
    """Web 搜索兜底（占位符）"""
    logger.warning("[WebSearch] Web 搜索未实现，返回空文档")
    state["documents"] = []
    return state


async def generate_answer(state: AgenticRAGState) -> AgenticRAGState:
    """生成答案"""
    query = state["query"]
    documents = state["documents"]
    chat_history = state.get("chat_history", [])

    # 构建 prompt
    context = "\n".join(d.get("document", "")[:500] for d in documents[:3])
    history_text = "\n".join(f"用户：{q}\n助手：{a}" for q, a in chat_history[-3:])

    prompt = f"""你是一个知识库问答助手。

对话历史：
{history_text}

相关文档：
{context}

用户问题：{query}

请基于上述信息回答用户问题。如果文档不足以回答，请明确说明。"""

    model = get_primary_text_chat_model()
    from langchain_core.messages import HumanMessage
    result = await model._agenerate([HumanMessage(content=prompt)])
    answer = result.generations[0].message.content

    state["answer"] = answer
    logger.info(f"[Generate] 生成答案: {answer[:50]}...")
    return state


async def self_reflect(state: AgenticRAGState) -> AgenticRAGState:
    """Self-RAG：评估答案质量"""
    answer = state["answer"]

    # 简化版：检查是否包含"不确定"、"无法回答"等
    if any(kw in answer for kw in ["不确定", "无法回答", "不知道", "没有相关信息"]):
        state["needs_retry"] = True
        logger.info("[Reflect] 答案质量不足，需要重试")
    else:
        state["needs_retry"] = False
        logger.info("[Reflect] 答案质量合格")

    return state


def build_agentic_rag_graph() -> StateGraph:
    """构建 Agentic RAG 状态图"""
    workflow = StateGraph(AgenticRAGState)

    # 添加节点
    workflow.add_node("route", route_query)
    workflow.add_node("retrieve", retrieve_documents)
    workflow.add_node("grade", grade_documents)
    workflow.add_node("web_search", web_search_fallback)
    workflow.add_node("generate", generate_answer)
    workflow.add_node("reflect", self_reflect)

    # 设置入口
    workflow.set_entry_point("route")

    # 路由逻辑
    workflow.add_conditional_edges(
        "route",
        lambda s: s["route"],
        {
            "vectorstore": "retrieve",
            "web_search": "web_search",
        }
    )

    workflow.add_edge("retrieve", "grade")

    workflow.add_conditional_edges(
        "grade",
        decide_next,
        {
            "generate": "generate",
            "web_search": "web_search",
        }
    )

    workflow.add_edge("web_search", "generate")
    workflow.add_edge("generate", "reflect")

    workflow.add_conditional_edges(
        "reflect",
        lambda s: "retrieve" if s["needs_retry"] and len(s["documents"]) < 10 else "end",
        {
            "retrieve": "retrieve",
            "end": END,
        }
    )

    return workflow.compile()


# 全局图实例
_agentic_graph = None


def get_agentic_rag_graph():
    """获取 Agentic RAG 图实例（单例）"""
    global _agentic_graph
    if _agentic_graph is None:
        _agentic_graph = build_agentic_rag_graph()
    return _agentic_graph
