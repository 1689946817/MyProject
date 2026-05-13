"""
Agentic RAG 专用评估器模块（P3-2）

本模块为 Agentic RAG（具有自我反思与重试能力的 RAG 系统）提供专项评估指标，
独立于 base_evaluator 的评估链体系，直接接收外部传入的 model 实例进行异步评估。

核心评估指标：
- Retry Rate（重试率）：衡量 Self-RAG 是否正确识别出需要重新检索的场景。
  高重试率说明检索质量不稳定或查询理解不足。
- Grounding Rate（接地率）：衡量生成答案是否忠实于检索到的文档，
  而非依赖模型自身知识"幻觉"生成。接地率越高，RAG 系统越可靠。

与 BaseEvaluator 的区别：
  - 不继承 BaseEvaluator / EvaluatorInterface，独立实现评估逻辑
  - 使用异步 run_evaluation，接收外部 model 实例而非内部构造
  - 不走 LangChain Chain，直接调用 model._agenerate
"""
from typing import Dict, List, Any

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field


class EvaluationResult(BaseModel):
    """评估结果数据模型。

    用于 JSON 输出解析器的 Pydantic schema，确保 LLM 输出包含 grade（YES/NO）和 reason（推理过程）。
    """
    grade: str = Field(description="the grade after evaluating the metric (YES or NO)")
    reason: str = Field(description="The reasoning behind the grading decision")


class BaseAgenticEvaluator:
    """Agentic 评估器基类。

    提供 JSON 解析器初始化和异步评估流程的公共实现。
    子类只需实现 get_prompt 方法，定义各自的评估提示词。

    属性:
        json_parser: 基于 EvaluationResult schema 的 JSON 输出解析器
        kwargs: 评估所需的参数字典（user_query、generated_answer、documents 等）
    """
    def __init__(self, **kwargs):
        self.json_parser = JsonOutputParser(pydantic_object=EvaluationResult)
        self.kwargs = kwargs

    def get_prompt(self, inputs: dict):
        """构建评估提示词（子类必须实现）。"""
        raise NotImplementedError

    async def run_evaluation(self, model) -> dict:
        """异步执行评估流程。

        流程：构建提示词 -> 调用 model._agenerate -> 解析 JSON -> 转换评分

        Args:
            model: LangChain ChatModel 实例（如 ChatOpenAI）。

        Returns:
            评估结果字典 {"grade": 0|1, "reason": "..."}。
        """
        prompt = self.get_prompt(self.kwargs)
        result = await model._agenerate([prompt])
        content = result.generations[0][0].text
        parsed = self.json_parser.parse(content)
        return {
            "grade": 1 if parsed["grade"].upper() == "YES" else 0,
            "reason": parsed["reason"],
        }


class RetryRateEvaluator(BaseAgenticEvaluator):
    """重试率评估器。

    评估 Agentic RAG 系统是否正确识别出需要重新检索的情况。
    判断依据：检索到的文档是否与问题相关、是否包含足够信息、生成答案是否表现出不确定性。

    属性:
        user_query: 用户原始问题
        generated_answer: RAG 系统生成的答案
        documents: 检索到的文档列表，每项含 "document" 字段
    """
    def __init__(self, user_query: str, generated_answer: str, documents: List[Dict[str, Any]]):
        super().__init__(
            user_query=user_query,
            generated_answer=generated_answer,
            documents=documents,
        )

    def get_prompt(self, inputs: dict):
        """构建重试率评估提示词。截取前 3 篇文档，每篇限 200 字符以控制 token 消耗。"""
        docs_text = "\n".join(
            f"[文档{i+1}] {d.get('document', '')[:200]}"
            for i, d in enumerate(inputs["documents"][:3])
        )

        message = {
            "type": "text",
            "text": (
                f"""
Evaluate the following metric:

retry_needed: Based on the retrieved documents, should the system retry retrieval to get better context? (YES or NO)

USER QUERY: "{inputs["user_query"]}"
RETRIEVED DOCUMENTS:
{docs_text}

GENERATED ANSWER: "{inputs["generated_answer"]}"

Criteria for YES (retry needed):
- Documents are irrelevant to the query
- Documents lack sufficient information to answer
- Answer shows uncertainty or inability to answer

Write out your reasoning step by step.
Give the reason as a string, not a list.
{self.json_parser.get_format_instructions()}
                """
            ),
        }
        return [HumanMessage(content=[message])]


class GroundingRateEvaluator(BaseAgenticEvaluator):
    """接地率（Grounding Rate）评估器。

    评估生成答案是否忠实于检索到的文档，检测模型是否"幻觉"编造了文档中不存在的信息。
    比 RetryRate 更严格：截取前 5 篇文档、每篇 300 字符，提供更充分的判断上下文。

    属性:
        user_query: 用户原始问题
        generated_answer: RAG 系统生成的答案
        documents: 检索到的文档列表，每项含 "document" 字段
    """
    def __init__(self, user_query: str, generated_answer: str, documents: List[Dict[str, Any]]):
        super().__init__(
            user_query=user_query,
            generated_answer=generated_answer,
            documents=documents,
        )

    def get_prompt(self, inputs: dict):
        """构建接地率评估提示词。截取前 5 篇文档，每篇限 300 字符。"""
        docs_text = "\n".join(
            f"[文档{i+1}] {d.get('document', '')[:300]}"
            for i, d in enumerate(inputs["documents"][:5])
        )

        message = {
            "type": "text",
            "text": (
                f"""
Evaluate the following metric:

grounding: Is the answer grounded in the retrieved documents, or is it hallucinated? (YES or NO)

USER QUERY: "{inputs["user_query"]}"
RETRIEVED DOCUMENTS:
{docs_text}

GENERATED ANSWER: "{inputs["generated_answer"]}"

Criteria for YES (grounded):
- Answer content can be traced back to the documents
- No fabricated facts or information not in documents
- Proper attribution or acknowledgment of document sources

Criteria for NO (hallucinated):
- Answer contains facts not present in documents
- Answer contradicts document content
- Answer makes up information

Write out your reasoning step by step.
Give the reason as a string, not a list.
{self.json_parser.get_format_instructions()}
                """
            ),
        }
        return [HumanMessage(content=[message])]


def calculate_retry_rate(evaluation_results: List[Dict[str, Any]]) -> float:
    """计算重试率：需要重试的样本占比。

    Args:
        evaluation_results: 评估结果列表，每项包含 retry_needed 字段（1=需要重试，0=不需要）。

    Returns:
        重试率（0-1），越高说明检索质量越不稳定。
    """
    if not evaluation_results:
        return 0.0

    retry_count = sum(1 for r in evaluation_results if r.get("retry_needed") == 1)
    return retry_count / len(evaluation_results)


def calculate_grounding_rate(evaluation_results: List[Dict[str, Any]]) -> float:
    """计算接地率：答案忠实于文档的样本占比。

    Args:
        evaluation_results: 评估结果列表，每项包含 grounding 字段（1=有接地，0=幻觉）。

    Returns:
        接地率（0-1），越高说明 RAG 系统越可靠。
    """
    if not evaluation_results:
        return 0.0

    grounded_count = sum(1 for r in evaluation_results if r.get("grounding") == 1)
    return grounded_count / len(evaluation_results)
