"""
LLaVA评估器模块

本模块包含基于LLaVA模型的各类评估器实现，用于评估RAG系统的输出质量。
每个评估器针对特定的评估指标设计，通过构建特定的提示词引导LLaVA进行评估。

支持的评估指标：
- Image Context Relevancy: 图像上下文相关性
- Image Faithfulness: 图像忠实度
- Text Context Relevancy: 文本上下文相关性
- Answer Relevancy: 答案相关性
- Answer Correctness: 答案正确性
- Text Faithfulness: 文本忠实度

LLaVA模型特点：
- 开源视觉语言模型，支持图像理解
- 使用[INST]...[/INST]格式的指令模板
- 支持<image>标记来指示图像输入位置
- 输出格式可能不稳定，需要格式修正

作者: [项目作者]
日期: [创建日期]
"""

import io
from evaluation.evaluators.base_evaluator import BaseEvaluator
from PIL import Image
from utils.base64_utils.base64_utils import decode_image_to_bytes


class ImageContextRelevancyEvaluator(BaseEvaluator):
    """
    图像上下文相关性评估器。
    
    评估检索到的图像是否与用户问题相关，即图像内容是否能够
    帮助回答用户的问题。这是评估检索系统质量的重要指标。
    
    评估标准：
    - YES: 图像内容与问题相关，能够提供有用信息
    - NO: 图像内容与问题无关，无法帮助回答问题
    
    属性:
        user_query: 用户问题
        image: 待评估的图像（base64编码）
        model: LLaVA模型实例
        tokenizer: LLaVA分词器实例
    
    使用示例:
        >>> evaluator = ImageContextRelevancyEvaluator(
        ...     user_query="What color is the LED?",
        ...     image="base64_encoded_image",
        ...     model=llava_model,
        ...     tokenizer=llava_tokenizer
        ... )
        >>> result = evaluator.run_evaluation()
    """
    def __init__(self, user_query: str, image: str, model, tokenizer) -> dict:
        """
        初始化图像上下文相关性评估器。
        
        :param user_query: 用户问题
        :param image: 图像的base64编码字符串
        :param model: LLaVA模型实例
        :param tokenizer: LLaVA分词器实例
        """
        super().__init__(model=model, user_query=user_query, image=image, tokenizer=tokenizer)
        
    def get_prompt(self, inputs: dict):
        """
        构建图像上下文相关性评估提示词。
        
        该方法构建发送给LLaVA的评估提示词，包含：
        1. 图像输入标记
        2. 评估任务说明
        3. 输出格式要求
        
        :param inputs: 包含user_query和image的字典
        
        :return: 包含prompt和image的字典
                 - prompt: 格式化的评估提示词
                 - image: PIL Image对象
        
        提示词格式:
            [INST] <image>
            Evaluate the following metric by comparing the user query with the provided image:
            image_context_relevancy: Is the content of the image relevant to the user's query? (YES or NO)
            {JSON格式说明}
            [/INST]
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
    """
    图像忠实度评估器。
    
    评估生成的答案是否与检索到的图像内容事实一致，即答案中的
    信息是否能够从图像中得到支持，不存在与图像矛盾的内容。
    
    评估标准：
    - YES: 答案内容与图像一致，没有虚构信息
    - NO: 答案包含图像中不存在或矛盾的信息
    
    这是检测幻觉（hallucination）的重要指标。
    
    属性:
        user_query: 用户问题
        generated_answer: RAG系统生成的答案
        image: 检索到的图像（base64编码）
        model: LLaVA模型实例
        tokenizer: LLaVA分词器实例
    """
    def __init__(self, user_query: str, generated_answer: str, image: str, model, tokenizer) -> dict:
        """
        初始化图像忠实度评估器。
        
        :param user_query: 用户问题
        :param generated_answer: RAG系统生成的答案
        :param image: 图像的base64编码字符串
        :param model: LLaVA模型实例
        :param tokenizer: LLaVA分词器实例
        """
        super().__init__(user_query=user_query, generated_answer=generated_answer, image=image, model=model, tokenizer=tokenizer)

    def get_prompt(self, inputs: dict):
        """
        构建图像忠实度评估提示词。
        
        该方法构建评估答案与图像是否事实一致的提示词，
        重点检查答案是否忠实于图像内容。
        
        :param inputs: 包含generated_answer和image的字典
        
        :return: 包含prompt和image的字典
        """
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
    """
    上下文相关性评估器（多模态版本）。
    
    同时评估文本和图像上下文是否与用户问题相关。
    这是一个综合性的评估器，适用于多模态RAG场景。
    
    属性:
        user_query: 用户问题
        context: 检索到的文本上下文
        image: 检索到的图像（base64编码）
        model: LLaVA模型实例
        tokenizer: LLaVA分词器实例
    """
    def __init__(self, user_query: str, context: str, image: str, model, tokenizer) -> dict:
        """
        初始化上下文相关性评估器。
        
        :param user_query: 用户问题
        :param context: 文本上下文
        :param image: 图像的base64编码字符串
        :param model: LLaVA模型实例
        :param tokenizer: LLaVA分词器实例
        """
        super().__init__(model=model, user_query=user_query, context=context, image=image, tokenizer=tokenizer)
        
    def get_prompt(self, inputs: dict):
        """
        构建多模态上下文相关性评估提示词。
        
        该方法构建同时评估文本和图像相关性的提示词。
        
        :param inputs: 包含user_query、context和image的字典
        
        :return: 包含prompt的字典
        """
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
    """
    文本上下文相关性评估器。
    
    评估检索到的文本是否与用户问题相关，即文本内容是否
    包含能够回答用户问题的信息。
    
    评估标准：
    - YES: 文本内容与问题相关，包含有用信息
    - NO: 文本内容与问题无关
    
    属性:
        user_query: 用户问题
        context: 检索到的文本上下文
        model: LLaVA模型实例
        tokenizer: LLaVA分词器实例
    """
    def __init__(self, user_query: str, context: str, model, tokenizer) -> dict:
        """
        初始化文本上下文相关性评估器。
        
        :param user_query: 用户问题
        :param context: 文本上下文
        :param model: LLaVA模型实例
        :param tokenizer: LLaVA分词器实例
        """
        super().__init__(model=model, user_query=user_query, context=context, tokenizer=tokenizer)
        
        
    def get_prompt(self, inputs: dict):
        """
        构建文本上下文相关性评估提示词。
        
        :param inputs: 包含user_query和context的字典
        
        :return: 包含prompt的字典
        """
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
    """
    答案相关性评估器。
    
    评估生成的答案是否与用户问题相关，即答案是否
    能够回应用户的问题意图，而不是答非所问。
    
    评估标准：
    - YES: 答案与问题相关，回应了问题意图
    - NO: 答案与问题无关，没有回应问题
    
    属性:
        user_query: 用户问题
        generated_answer: RAG系统生成的答案
        model: LLaVA模型实例
        tokenizer: LLaVA分词器实例
    """
    def __init__(self, user_query: str, generated_answer: str, model, tokenizer) -> dict:
        """
        初始化答案相关性评估器。
        
        :param user_query: 用户问题
        :param generated_answer: RAG系统生成的答案
        :param model: LLaVA模型实例
        :param tokenizer: LLaVA分词器实例
        """
        super().__init__(model=model, user_query=user_query, generated_answer=generated_answer, tokenizer=tokenizer)
        
    
    def get_prompt(self, inputs: dict):
        """
        构建答案相关性评估提示词。
        
        :param inputs: 包含user_query和generated_answer的字典
        
        :return: 包含prompt的字典
        """
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
    """
    答案正确性评估器。
    
    将生成的答案与标准答案（ground truth）进行对比，
    评估生成答案的正确性。采用类似教师批改学生答案的方式。
    
    评估标准：
    - YES: 答案正确，与标准答案一致或包含标准答案内容
    - NO: 答案错误，与标准答案不一致
    
    评估原则：
    - 忽略标点符号和措辞差异
    - 允许答案包含额外信息，但不能有冲突内容
    
    属性:
        user_query: 用户问题
        generated_answer: RAG系统生成的答案（学生答案）
        reference_answer: 标准答案（参考答案）
        model: LLaVA模型实例
        tokenizer: LLaVA分词器实例
    """
    def __init__(self, user_query: str, generated_answer: str, reference_answer: str, model, tokenizer) -> dict:
        """
        初始化答案正确性评估器。
        
        :param user_query: 用户问题
        :param generated_answer: RAG系统生成的答案
        :param reference_answer: 标准答案
        :param model: LLaVA模型实例
        :param tokenizer: LLaVA分词器实例
        """
        super().__init__(model=model, user_query=user_query, reference_answer=reference_answer,
                         generated_answer=generated_answer, tokenizer=tokenizer)
         
    def get_prompt(self, inputs: dict):
        """
        构建答案正确性评估提示词。
        
        采用教师批改学生答案的角色扮演方式，
        使评估更加准确和可解释。
        
        :param inputs: 包含user_query、generated_answer和reference_answer的字典
        
        :return: 包含prompt的字典
        """
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
    """
    文本忠实度评估器。
    
    评估生成的答案是否与检索到的文本上下文事实一致，
    即答案中的信息是否能够从文本中得到支持，不存在幻觉。
    
    评估标准：
    - YES: 答案内容与文本一致，没有虚构信息
    - NO: 答案包含文本中不存在或矛盾的信息
    
    这是检测文本幻觉的重要指标，对于RAG系统的可靠性至关重要。
    
    属性:
        user_query: 用户问题
        generated_answer: RAG系统生成的答案
        context: 检索到的文本上下文
        model: LLaVA模型实例
        tokenizer: LLaVA分词器实例
    """
    def __init__(self, user_query: str, generated_answer: str, context: str, model, tokenizer) -> dict:
        """
        初始化文本忠实度评估器。
        
        :param user_query: 用户问题
        :param generated_answer: RAG系统生成的答案
        :param context: 文本上下文
        :param model: LLaVA模型实例
        :param tokenizer: LLaVA分词器实例
        """
        super().__init__(user_query=user_query, generated_answer=generated_answer, context=context, model=model, tokenizer=tokenizer)
        
    def get_prompt(self, inputs: dict):
        """
        构建文本忠实度评估提示词。
        
        该方法构建评估答案与文本是否事实一致的提示词，
        重点检查答案是否忠实于文本内容，是否存在幻觉。
        
        :param inputs: 包含generated_answer和context的字典
        
        :return: 包含prompt的字典
        """
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
