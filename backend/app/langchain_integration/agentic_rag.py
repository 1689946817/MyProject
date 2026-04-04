"""
Agentic RAG 模块（基于 LangGraph）

实现三种 Agentic 模式：
1. 查询路由：判断查询类型，选择检索策略
2. CRAG（Corrective RAG）：检索后评估相关性，必要时重新检索或 Web 搜索
3. Self-RAG：生成后自我评估，决定是否需要更多检索
"""
import logging
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.core.config import settings
from app.langchain_integration.models import get_chat_model

logger = logging.getLogger(__name__)


class AgenticRAGState(TypedDict):
    """Agentic RAG 状态"""
    query: str
    chat_history: List[tuple]
    documents: List[Dict[str, Any]]
    answer: str
    route: str  # "vectorstore" | "web_search"
    relevance_score: float  # 0-1
    needs_retry: bool


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

    model = get_chat_model()
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
