"""
OpenAI（GPT-4o）评估器模块。

本模块包含基于 OpenAI GPT-4o 模型的各类评估器实现，用于评估 RAG 系统的输出质量。
所有评估器继承 BaseEvaluator，通过 get_prompt 构建包含文本/图像的多模态 HumanMessage，
由 BaseEvaluator 的评估链自动完成 LLM 调用、JSON 解析和评分转换。

支持的评估指标：
- Text Context Relevancy: 检索到的文本是否与用户问题相关
- Image Context Relevancy: 检索到的图像是否与用户问题相关
- Answer Relevancy: 生成的答案是否与用户问题相关
- Answer Correctness: 生成的答案是否与标准答案一致
- Image Faithfulness: 生成的答案是否忠实于图像内容（检测图像幻觉）
- Text Faithfulness: 生成的答案是否忠实于文本上下文（检测文本幻觉）

与 LLaVA 评估器的区别：
  - 返回 HumanMessage 列表（而非 dict），直接传给 ChatOpenAI 模型
  - 支持 base64 图像通过 image_url content block 嵌入提示词
  - 无需手动解析 JSON，由 BaseEvaluator 的 json_parser 自动处理
"""

from langchain_core.messages import HumanMessage
from evaluation.evaluators.base_evaluator import BaseEvaluator


class TextContextRelevancyEvaluator(BaseEvaluator):
    """文本上下文相关性评估器（OpenAI 版）。

    评估检索到的文本上下文是否与用户问题相关。
    纯文本评估，不涉及图像。
    """
    def __init__(self, user_query: str, context: str):
        super().__init__(user_query=user_query, context=context)

    def get_prompt(self, inputs: dict):
        """构建纯文本评估提示词，返回 HumanMessage 列表。"""
        message = {
            "type": "text",
            "text": (
                f"""
            Evaluate the following metric:

            text_context_relevancy: Is the context provided by the text "{inputs["context"]}" relevant to the user's query "{inputs["user_query"]}"? (YES or NO)

            Write out in a step by step manner your reasoning to be sure that your conclusion is correct.
            Give the reason as a string, not a list.
            {self.json_parser.get_format_instructions()}
            """
            ),
        }
        return [HumanMessage(content=[message])]


class ImageContextRelevancyEvaluator(BaseEvaluator):
    """图像上下文相关性评估器（OpenAI 版）。

    评估检索到的图像是否与用户问题相关。
    图像以 base64 编码通过 image_url content block 传入 GPT-4o。
    """
    def __init__(self, user_query: str, image: str):
        super().__init__(user_query=user_query, image=[image])

    def get_prompt(self, inputs: dict):
        """构建包含图像的多模态评估提示词。图像置于文本之前，符合 GPT-4o 的视觉输入习惯。"""
        messages = []
        for image in inputs["image"]:
            messages.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image}"},
            })
        messages.append({
            "type": "text",
            "text": (
                f"""
            Evaluate the following metric:

            image_context_relevancy: Is the context provided by the image(s) relevant to the user's query "{inputs["user_query"]}"? (YES or NO)

            Write out in a step by step manner your reasoning to be sure that your conclusion is correct.
            Give the reason as a string, not a list.
            {self.json_parser.get_format_instructions()}
            """
            ),
        })
        return [HumanMessage(content=messages)]


class AnswerRelevancyEvaluator(BaseEvaluator):
    """答案相关性评估器（OpenAI 版）。

    评估生成的答案是否与用户问题相关，即是否回应了用户的意图。
    纯文本评估，不涉及图像。
    """
    def __init__(self, user_query: str, generated_answer: str):
        super().__init__(user_query=user_query, generated_answer=generated_answer)

    def get_prompt(self, inputs: dict):
        """构建纯文本评估提示词。"""
        message = {
            "type": "text",
            "text": (
                f"""
            Evaluate the following metric:

            answer_relevancy: Is the answer "{inputs["generated_answer"]}" relevant to the user's query "{inputs["user_query"]}"? (YES or NO)

            Write out in a step by step manner your reasoning to be sure that your conclusion is correct.
            Give the reason as a string, not a list.
            {self.json_parser.get_format_instructions()}
            """
            ),
        }
        return [HumanMessage(content=[message])]


class AnswerCorrectnessEvaluator(BaseEvaluator):
    """答案正确性评估器（OpenAI 版）。

    将生成答案与标准答案进行对比，采用"教师批改"角色扮演方式。
    允许答案包含额外信息，只要不与标准答案冲突。

    属性:
        user_query: 用户问题
        generated_answer: RAG 系统生成的答案（学生答案）
        reference_answer: 标准答案（ground truth）
    """
    def __init__(self, user_query: str, generated_answer: str, reference_answer: str):
        super().__init__(user_query=user_query, generated_answer=generated_answer, reference_answer=reference_answer)

    def get_prompt(self, inputs: dict):
        """构建教师批改式评估提示词。"""
        message = {
            "type": "text",
            "text": (
                f"""
                You are given a question, the correct reference answer, and the student's answer.                 You are asked to grade the student's answer as either correct or incorrect, based on the reference answer.                 Ignore differences in punctuation and phrasing between the student answer and true answer.                 It is OK if the student answer contains more information than the true answer, as long as it does not contain any conflicting statements.                USER QUERY: "{inputs["user_query"]}"
                REFERENCE ANSWER: "{inputs["reference_answer"]}"
                STUDENT ANSWER: "{inputs["generated_answer"]}"
                answer_correctness: Is the student's answer correct? (YES or NO)

                Write out in a step by step manner your reasoning to be sure that your conclusion is correct.
                Give the reason as a string, not a list.
                {self.json_parser.get_format_instructions()}
                """
            ),
        }
        return [HumanMessage(content=[message])]


class ImageFaithfulnessEvaluator(BaseEvaluator):
    """图像忠实度评估器（OpenAI 版）。

    评估生成答案是否忠实于检索到的图像内容，检测图像幻觉。
    如果没有图像输入，返回 None 跳过评估。
    """
    def __init__(self, user_query: str, generated_answer: str, image: str):
        super().__init__(user_query=user_query, generated_answer=generated_answer, image=[image])

    def get_prompt(self, inputs: dict):
        """构建图像忠实度评估提示词。无图像时返回 None 表示跳过。"""
        if not inputs["image"]:
            return None
        messages = []
        for image in inputs["image"]:
            messages.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image}"},
            })
        messages.append({
            "type": "text",
            "text": (
                f"""
                Evaluate the following metric:

                image_faithfulness: Is the answer faithful to the context provided by the image(s), i.e. does it factually align with the context? (YES or NO)

                ANSWER: "{inputs["generated_answer"]}"
                Write out in a step by step manner your reasoning to be sure that your conclusion is correct.
                Give the reason as a string, not a list.
                {self.json_parser.get_format_instructions()}
                """
            ),
        })
        return [HumanMessage(content=messages)]


class TextFaithfulnessEvaluator(BaseEvaluator):
    """文本忠实度评估器（OpenAI 版）。

    评估生成答案是否忠实于检索到的文本上下文，检测文本幻觉。
    纯文本评估，不涉及图像。
    """
    def __init__(self, user_query: str, generated_answer: str, context: str):
        super().__init__(user_query=user_query, generated_answer=generated_answer, context=context)

    def get_prompt(self, inputs: dict):
        """构建文本忠实度评估提示词。"""
        message = {
            "type": "text",
            "text": (
                f"""
                Evaluate the following metric:

                text_faithfulness: Is the answer faithful to the context, i.e. does it factually align with the context? (YES or NO)

                CONTEXT: "{inputs["context"]}"
                ANSWER: "{inputs["generated_answer"]}"
                Write out in a step by step manner your reasoning to be sure that your conclusion is correct.
                Give the reason as a string, not a list.
                {self.json_parser.get_format_instructions()}
                """
            ),
        }
        return [HumanMessage(content=[message])]
