"""
LLaVA 评估器模块。

本模块包含基于 LLaVA（开源视觉语言模型）的各类评估器实现，用于评估 RAG 系统的输出质量。
所有评估器继承 BaseEvaluator，通过 get_prompt 构建 LLaVA 特有的 [INST]...[/INST] 指令模板。

LLaVA 模型特点：
- 开源视觉语言模型，支持图像理解
- 使用 [INST]...[/INST] 格式的指令模板
- 使用 <image> 标记指示图像输入位置
- 输出格式可能不稳定，需要 BaseEvaluator.fix_format_parser 修正

支持的评估指标：
- Image Context Relevancy: 检索到的图像是否与用户问题相关
- Image Faithfulness: 生成答案是否忠实于图像内容
- Text Context Relevancy: 检索到的文本是否与用户问题相关
- Answer Relevancy: 生成的答案是否与用户问题相关
- Answer Correctness: 生成答案是否与标准答案一致
- Text Faithfulness: 生成答案是否忠实于文本上下文

与 OpenAI 评估器的区别：
  - 返回 {"prompt": ..., "image": ...} 字典（而非 HumanMessage 列表）
  - 图像通过 PIL Image 对象传入（而非 base64 字符串）
  - 需要 decode_image_to_bytes 将 base64 转为 PIL Image
"""

import io
from evaluation.evaluators.base_evaluator import BaseEvaluator
from PIL import Image
from utils.base64_utils.base64_utils import decode_image_to_bytes


class ImageContextRelevancyEvaluator(BaseEvaluator):
    """图像上下文相关性评估器（LLaVA 版）。

    评估检索到的图像是否与用户问题相关，即图像内容是否能够帮助回答用户的问题。
    这是评估检索系统质量的重要指标。

    评估标准：
    - YES: 图像内容与问题相关，能够提供有用信息
    - NO: 图像内容与问题无关，无法帮助回答问题

    属性:
        user_query: 用户问题
        image: 待评估的图像（base64 编码字符串）
    """
    def __init__(self, user_query: str, image: str, model, tokenizer) -> dict:
        """初始化图像上下文相关性评估器。

        :param user_query: 用户问题
        :param image: 图像的 base64 编码字符串
        :param model: LLaVA 模型实例
        :param tokenizer: LLaVA 分词器实例
        """
        super().__init__(model=model, user_query=user_query, image=image, tokenizer=tokenizer)

    def get_prompt(self, inputs: dict):
        """构建图像上下文相关性评估提示词。

        将 base64 图像解码为 PIL Image，配合 [INST]...[/INST] 模板构建 LLaVA 输入。

        :param inputs: 包含 user_query 和 image 的字典
        :return: {"prompt": str, "image": PIL.Image} 或 None（无图像时）
        """
        if not inputs["image"]:
            return None

        json_format = "{grade: '', 'reason': ''}"

        prompt = f"""
            [INST] {'<image>' if inputs['image'] else ' '}\n
            Evaluate the following metric by comparing the user query with the provided image:\n
            image_context_relevancy: Is the content of the image relevant to the user\'s query "{inputs["user_query"]}", i.e. can it contribute to answer the query? (YES or NO)\n
            Write out in a step by step manner your reasoning to be sure that your conclusion is correct by filling out the following JSON format with the grade and a concise reason behind the grade:
            {json_format}
            Output the reason as a string, not as a list.
            The only allowed grades are YES or NO. [/INST]
            """

        image = decode_image_to_bytes(inputs['image'])
        image = Image.open(io.BytesIO(image))

        return {"prompt": prompt, "image": image}


class ImageFaithfulnessEvaluator(BaseEvaluator):
    """图像忠实度评估器（LLaVA 版）。

    评估生成的答案是否与检索到的图像内容事实一致，检测图像幻觉。
    答案中的信息必须能从图像中得到支持，不能存在矛盾内容。

    评估标准：
    - YES: 答案内容与图像一致，没有虚构信息
    - NO: 答案包含图像中不存在或矛盾的信息

    属性:
        user_query: 用户问题
        generated_answer: RAG 系统生成的答案
        image: 检索到的图像（base64 编码字符串）
    """
    def __init__(self, user_query: str, generated_answer: str, image: str, model, tokenizer) -> dict:
        super().__init__(user_query=user_query, generated_answer=generated_answer, image=image, model=model, tokenizer=tokenizer)

    def get_prompt(self, inputs: dict):
        """构建图像忠实度评估提示词。无图像时返回 None。"""
        if not inputs["image"]:
            return None

        json_format = "\{grade: '', 'reason': ''}"

        prompt = f"""
            [INST] {'<image>' if inputs['image'] else ' '}\n
            Evaluate the following metric by comparing the answer with the provided image:\n
            image_faithfulness: Is the answer faithful to the content of the image, i.e. does it factually align with the image? (YES or NO)\n
            ANSWER: "{inputs["generated_answer"]}"\n\
            Write out in a step by step manner your reasoning to be sure that your conclusion is correct by filling out the following JSON format with the grade and a concise reason behind the grade:
            {json_format}
            Output the reason as a string, not as a list.
            The only allowed grades are YES or NO. [/INST]
            """

        image = decode_image_to_bytes(inputs['image'])
        image = Image.open(io.BytesIO(image))

        return {"prompt": prompt, "image": image}
    
    
class ContextRelevancyEvaluator(BaseEvaluator):
    """多模态上下文相关性评估器（LLaVA 版）。

    同时评估文本和图像上下文是否与用户问题相关，适用于多模态 RAG 场景。
    注意：此评估器不传入图像，仅通过文本上下文评估相关性。

    属性:
        user_query: 用户问题
        context: 检索到的文本上下文
        image: 检索到的图像（base64 编码字符串）
    """
    def __init__(self, user_query: str, context: str, image: str, model, tokenizer) -> dict:
        super().__init__(model=model, user_query=user_query, context=context, image=image, tokenizer=tokenizer)

    def get_prompt(self, inputs: dict):
        """构建多模态上下文相关性评估提示词。仅返回纯文本 prompt，不传图像。"""
        json_format = "\{grade: '', 'reason': ''}"
        
        prompt = f"""
            [INST] Evaluate the following metric by comparing the user query with the provided image and text:\n\n
            context_relevancy: Is the context provided (as text and/or image) relevant to the user\'s query? (YES or NO)\n
            USER QUERY: {inputs["user_query"]}\n
            {"TEXT: " + inputs["context"] if inputs["context"] else ""}
            Write out in a step by step manner your reasoning to be sure that your conclusion is correct by filling out the following JSON format with the grade and a concise reason behind the grade:
            {json_format}
            Output the reason as a string, not as a list.
            The only allowed grades are YES or NO. [/INST]
            """
        
        return {"prompt": prompt}


class TextContextRelevancyEvaluator(BaseEvaluator):
    """文本上下文相关性评估器（LLaVA 版）。

    评估检索到的文本是否与用户问题相关，即文本内容是否包含能够回答用户问题的信息。

    评估标准：
    - YES: 文本内容与问题相关，包含有用信息
    - NO: 文本内容与问题无关

    属性:
        user_query: 用户问题
        context: 检索到的文本上下文
    """
    def __init__(self, user_query: str, context: str, model, tokenizer) -> dict:
        super().__init__(model=model, user_query=user_query, context=context, tokenizer=tokenizer)


    def get_prompt(self, inputs: dict):
        """构建文本上下文相关性评估提示词。纯文本评估，无图像输入。"""
        json_format = "\{grade: '', 'reason': ''}"
        
        prompt = f"""
            [INST] Evaluate the following metric:\n
            text_context_relevancy: Is the text "{inputs["context"]}" relevant to the user\'s query "{inputs["user_query"]}"? (YES or NO)\n
            Write out in a step by step manner your reasoning to be sure that your conclusion is correct by filling out the following JSON format with the grade and a concise reason behind the grade:
            {json_format}
            Output the reason as a string, not as a list.
            The only allowed grades are YES or NO. [/INST]
            """
        
        return {"prompt": prompt}


class AnswerRelevancyEvaluator(BaseEvaluator):
    """答案相关性评估器（LLaVA 版）。

    评估生成的答案是否与用户问题相关，即答案是否回应了用户的问题意图。

    评估标准：
    - YES: 答案与问题相关，回应了问题意图
    - NO: 答案与问题无关，答非所问

    属性:
        user_query: 用户问题
        generated_answer: RAG 系统生成的答案
    """
    def __init__(self, user_query: str, generated_answer: str, model, tokenizer) -> dict:
        super().__init__(model=model, user_query=user_query, generated_answer=generated_answer, tokenizer=tokenizer)


    def get_prompt(self, inputs: dict):
        """构建答案相关性评估提示词。纯文本评估。"""
        json_format = "\{grade: '', 'reason': ''}"
        
        prompt = f"""
            [INST] Evaluate the following metric:\n
            answer_relevancy: Is the answer "{inputs["generated_answer"]}" relevant to the user\'s query "{inputs["user_query"]}"? (YES or NO)\n
            Write out in a step by step manner your reasoning to be sure that your conclusion is correct by filling out the following JSON format with the grade and a concise reason behind the grade:
            {json_format}
            Output the reason as a string, not as a list.
            The only allowed grades are YES or NO. [/INST]
            """
        
        return {"prompt": prompt}


class AnswerCorrectnessEvaluator(BaseEvaluator):
    """答案正确性评估器（LLaVA 版）。

    将生成答案与标准答案对比，采用"教师批改学生答案"角色扮演方式。
    评估原则：
    - 忽略标点符号和措辞差异
    - 允许答案包含额外信息，但不能有冲突内容

    属性:
        user_query: 用户问题
        generated_answer: RAG 系统生成的答案（学生答案）
        reference_answer: 标准答案（参考答案）
    """
    def __init__(self, user_query: str, generated_answer: str, reference_answer: str, model, tokenizer) -> dict:
        super().__init__(model=model, user_query=user_query, reference_answer=reference_answer,
                         generated_answer=generated_answer, tokenizer=tokenizer)

    def get_prompt(self, inputs: dict):
        """构建教师批改式评估提示词。"""
        json_format = "\{grade: '', 'reason': ''}"
        
        prompt = f"""
            [INST] You are given a question, the correct reference answer, and the student\'s answer. \
            You are asked to grade the student\'s answer as either correct or incorrect, based on the reference answer. \
            Ignore differences in punctuation and phrasing between the student answer and true answer. \
            It is OK if the student answer contains more information than the true answer, as long as it does not contain any conflicting statements.\
            USER QUERY: "{inputs["user_query"]}"\n\
            REFERENCE ANSWER: "{inputs["reference_answer"]}"\n\
            STUDENT ANSWER: "{inputs["generated_answer"]}"\n\
            answer_correctness: Is the student's answer correct? (YES or NO)\n
            Write out in a step by step manner your reasoning to be sure that your conclusion is correct by filling out the following JSON format with the grade and a concise reason behind the grade:
            {json_format}
            Output the reason as a string, not as a list.
            The only allowed grades are YES or NO. [/INST]
            """
        
        return {"prompt": prompt}


class TextFaithfulnessEvaluator(BaseEvaluator):
    """文本忠实度评估器（LLaVA 版）。

    评估生成的答案是否与检索到的文本上下文事实一致，检测文本幻觉。
    答案中的信息必须能从文本中得到支持，不能有矛盾。

    评估标准：
    - YES: 答案内容与文本一致，没有虚构信息
    - NO: 答案包含文本中不存在或矛盾的信息

    属性:
        user_query: 用户问题
        generated_answer: RAG 系统生成的答案
        context: 检索到的文本上下文
    """
    def __init__(self, user_query: str, generated_answer: str, context: str, model, tokenizer) -> dict:
        super().__init__(user_query=user_query, generated_answer=generated_answer, context=context, model=model, tokenizer=tokenizer)

    def get_prompt(self, inputs: dict):
        """构建文本忠实度评估提示词。纯文本评估。"""
        json_format = "\{grade: '', 'reason': ''}"
        
        prompt = f"""
            [INST] Evaluate the following metric:\n
            text_faithfulness: Is the answer faithful to the context provided by the text, i.e. does it factually align with the context? (YES or NO)\n
            ANSWER: "{inputs["generated_answer"]}"\n\
            TEXT: "{inputs["context"]}"\n\
            Write out in a step by step manner your reasoning to be sure that your conclusion is correct by filling out the following JSON format with the grade and a concise reason behind the grade:
            {json_format}
            Output the reason as a string, not as a list.
            The only allowed grades are YES or NO. [/INST]
            """
        
        return {"prompt": prompt}
