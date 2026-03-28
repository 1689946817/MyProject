"""
OpenAI评估器模块

本模块包含基于GPT-4V模型的各类评估器实现，用于评估RAG系统的输出质量。
支持的评估指标：
- Text Context Relevancy: 文本上下文相关性
- Image Context Relevancy: 图像上下文相关性
- Answer Relevancy: 答案相关性
- Answer Correctness: 答案正确性
- Image Faithfulness: 图像忠实度
- Text Faithfulness: 文本忠实度
"""

from langchain_core.messages import HumanMessage
from evaluation.evaluators.base_evaluator import BaseEvaluator


class TextContextRelevancyEvaluator(BaseEvaluator):
    def __init__(self, user_query: str, context: str):
        super().__init__(user_query=user_query, context=context)

    def get_prompt(self, inputs: dict):
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
    def __init__(self, user_query: str, image: str):
        super().__init__(user_query=user_query, image=[image])

    def get_prompt(self, inputs: dict):
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
    def __init__(self, user_query: str, generated_answer: str):
        super().__init__(user_query=user_query, generated_answer=generated_answer)

    def get_prompt(self, inputs: dict):
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
    def __init__(self, user_query: str, generated_answer: str, reference_answer: str):
        super().__init__(user_query=user_query, generated_answer=generated_answer, reference_answer=reference_answer)

    def get_prompt(self, inputs: dict):
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
    def __init__(self, user_query: str, generated_answer: str, image: str):
        super().__init__(user_query=user_query, generated_answer=generated_answer, image=[image])

    def get_prompt(self, inputs: dict):
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
    def __init__(self, user_query: str, generated_answer: str, context: str):
        super().__init__(user_query=user_query, generated_answer=generated_answer, context=context)

    def get_prompt(self, inputs: dict):
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
