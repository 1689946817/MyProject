"""
扩展评估器模块（P3-2）

新增 Agentic RAG 专用指标：
- Retry Rate（重试率）：Self-RAG 触发重新检索的比例
- Grounding Rate（接地率）：答案基于检索文档的比例（非幻觉）
"""
from typing import Dict, List, Any

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field


class EvaluationResult(BaseModel):
    """评估结果数据模型"""
    grade: str = Field(description="the grade after evaluating the metric (YES or NO)")
    reason: str = Field(description="The reasoning behind the grading decision")


class BaseAgenticEvaluator:
    """简化的 Agentic 评估器基类"""
    def __init__(self, **kwargs):
        self.json_parser = JsonOutputParser(pydantic_object=EvaluationResult)
        self.kwargs = kwargs

    def get_prompt(self, inputs: dict):
        raise NotImplementedError

    async def run_evaluation(self, model) -> dict:
        """运行评估"""
        prompt = self.get_prompt(self.kwargs)
        result = await model._agenerate([prompt])
        content = result.generations[0][0].text
        parsed = self.json_parser.parse(content)
        return {
            "grade": 1 if parsed["grade"].upper() == "YES" else 0,
            "reason": parsed["reason"],
        }


class RetryRateEvaluator(BaseAgenticEvaluator):
    """
    重试率评估器

    评估 Agentic RAG 系统是否正确识别出需要重新检索的情况。
    """
    def __init__(self, user_query: str, generated_answer: str, documents: List[Dict[str, Any]]):
        super().__init__(
            user_query=user_query,
            generated_answer=generated_answer,
            documents=documents,
        )

    def get_prompt(self, inputs: dict):
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
    """
    接地率评估器

    评估答案是否基于检索到的文档，而非模型幻觉。
    """
    def __init__(self, user_query: str, generated_answer: str, documents: List[Dict[str, Any]]):
        super().__init__(
            user_query=user_query,
            generated_answer=generated_answer,
            documents=documents,
        )

    def get_prompt(self, inputs: dict):
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
    """
    计算重试率：需要重试的样本占比

    Args:
        evaluation_results: 评估结果列表，每项包含 retry_needed 字段

    Returns:
        重试率（0-1）
    """
    if not evaluation_results:
        return 0.0

    retry_count = sum(1 for r in evaluation_results if r.get("retry_needed") == 1)
    return retry_count / len(evaluation_results)


def calculate_grounding_rate(evaluation_results: List[Dict[str, Any]]) -> float:
    """
    计算接地率：答案基于文档的样本占比

    Args:
        evaluation_results: 评估结果列表，每项包含 grounding 字段

    Returns:
        接地率（0-1）
    """
    if not evaluation_results:
        return 0.0

    grounded_count = sum(1 for r in evaluation_results if r.get("grounding") == 1)
    return grounded_count / len(evaluation_results)
