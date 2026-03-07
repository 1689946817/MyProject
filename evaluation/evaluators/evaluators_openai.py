"""
OpenAI评估器模块

本模块包含基于GPT-4V模型的各类评估器实现，用于评估RAG系统的输出质量。
每个评估器针对特定的评估指标设计，通过构建特定的消息格式引导GPT-4V进行评估。

支持的评估指标：
- Text Context Relevancy: 文本上下文相关性
- Image Context Relevancy: 图像上下文相关性
- Answer Relevancy: 答案相关性
- Answer Correctness: 答案正确性
- Image Faithfulness: 图像忠实度
- Text Faithfulness: 文本忠实度

GPT-4V模型特点：
- OpenAI的视觉语言模型，通过Azure API调用
- 使用HumanMessage格式传递消息
- 支持多模态输入（文本和图像）
- 输出格式稳定，JSON解析可靠
- 图像通过base64编码嵌入消息中

消息格式说明：
- 文本消息: {"type": "text", "text": "..."}
- 图像消息: {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
- 多条消息组成一个HumanMessage的content列表

作者: [项目作者]
日期: [创建日期]
"""

from langchain_core.messages import HumanMessage
from evaluation.evaluators.base_evaluator import BaseEvaluator


class TextContextRelevancyEvaluator(BaseEvaluator):
    """
    文本上下文相关性评估器（GPT-4V版本）。
    
    评估检索到的文本是否与用户问题相关，即文本内容是否
    包含能够回答用户问题的信息。
    
    评估标准：
    - YES: 文本内容与问题相关，包含有用信息
    - NO: 文本内容与问题无关
    
    与LLaVA版本的区别：
    - 使用HumanMessage格式而非[INST]模板
    - 通过json_parser.get_format_instructions()获取格式说明
    - 输出格式更稳定可靠
    
    属性:
        user_query: 用户问题
        context: 检索到的文本上下文
        model: GPT-4V模型实例（AzureChatOpenAI）
    """
    def __init__(self, user_query: str, context: str, model):
        """
        初始化文本上下文相关性评估器。
        
        :param user_query: 用户问题
        :param context: 文本上下文
        :param model: GPT-4V模型实例
        """
        super().__init__(model=model, user_query=user_query, context=context)

    def get_prompt(self, inputs: dict):
        """
        构建文本上下文相关性评估提示词。
        
        该方法构建发送给GPT-4V的消息格式，包含：
        1. 评估任务说明
        2. 用户问题和文本上下文
        3. JSON输出格式说明
        
        :param inputs: 包含user_query和context的字典
        
        :return: HumanMessage列表，包含评估提示词
        
        消息格式示例:
            HumanMessage(content=[
                {
                    "type": "text",
                    "text": "Evaluate the following metric:\\n
                             text_context_relevancy: Is the text relevant to the query? (YES or NO)\\n
                             {format_instructions}"
                }
            ])
        """
        message = {
            "type": "text",
            "text": (
                f"""
            Evaluate the following metric:\n
            text_context_relevancy: Is the context provided by the text "{inputs["context"]}" relevant to the user\'s query "{inputs["user_query"]}"? (YES or NO)\n
            Write out in a step by step manner your reasoning to be sure that your conclusion is correct.
            Give the reason as a string, not a list.
            {self.json_parser.get_format_instructions()}
            """
            ),
        }

        return [HumanMessage(content=[message])]


class ImageContextRelevancyEvaluator(BaseEvaluator):
    """
    图像上下文相关性评估器（GPT-4V版本）。
    
    评估检索到的图像是否与用户问题相关，即图像内容是否能够
    帮助回答用户的问题。
    
    评估标准：
    - YES: 图像内容与问题相关，能够提供有用信息
    - NO: 图像内容与问题无关，无法帮助回答问题
    
    图像传递方式：
    - 图像通过base64编码嵌入消息中
    - 使用data URI格式: data:image/jpeg;base64,{base64_string}
    
    属性:
        user_query: 用户问题
        image: 待评估的图像（base64编码列表）
        model: GPT-4V模型实例
    """
    def __init__(self, user_query: str, image: str, model):
        """
        初始化图像上下文相关性评估器。
        
        :param user_query: 用户问题
        :param image: 图像的base64编码字符串
        :param model: GPT-4V模型实例
        """
        super().__init__(model=model, user_query=user_query, image=[image])

    def get_prompt(self, inputs: dict):
        """
        构建图像上下文相关性评估提示词。
        
        该方法构建包含图像和文本的多模态消息：
        1. 图像消息（base64编码）
        2. 评估任务文本消息
        3. JSON输出格式说明
        
        :param inputs: 包含user_query和image列表的字典
        
        :return: HumanMessage列表，包含图像和评估提示词
        
        消息格式示例:
            HumanMessage(content=[
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
                {"type": "text", "text": "Evaluate the following metric..."}
            ])
        """
        messages = []
        for image in inputs['image']:
            image_message = {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image}"},
            }
            messages.append(image_message)

        text_message = {
            "type": "text",
            "text": (
                f"""
            Evaluate the following metric:\n
            image_context_relevancy: Is the context provided by the image(s) relevant to the user\'s query "{inputs["user_query"]}"? (YES or NO)\n
            Write out in a step by step manner your reasoning to be sure that your conclusion is correct.
            Give the reason as a string, not a list.
            {self.json_parser.get_format_instructions()}
            """
            ),
        }

        messages.append(text_message)
        return [HumanMessage(content=messages)]


class AnswerRelevancyEvaluator(BaseEvaluator):
    """
    答案相关性评估器（GPT-4V版本）。
    
    评估生成的答案是否与用户问题相关，即答案是否
    能够回应用户的问题意图，而不是答非所问。
    
    评估标准：
    - YES: 答案与问题相关，回应了问题意图
    - NO: 答案与问题无关，没有回应问题
    
    属性:
        user_query: 用户问题
        generated_answer: RAG系统生成的答案
        model: GPT-4V模型实例
    """
    def __init__(self, user_query: str, generated_answer: str, model):
        """
        初始化答案相关性评估器。
        
        :param user_query: 用户问题
        :param generated_answer: RAG系统生成的答案
        :param model: GPT-4V模型实例
        """
        super().__init__(model=model, user_query=user_query, generated_answer=generated_answer)

    def get_prompt(self, inputs: dict):
        """
        构建答案相关性评估提示词。
        
        :param inputs: 包含user_query和generated_answer的字典
        
        :return: HumanMessage列表
        """
        message = {
            "type": "text",
            "text": (
                f"""
            Evaluate the following metric:\n
            answer_relevancy: Is the answer "{inputs["generated_answer"]}" relevant to the user\'s query "{inputs["user_query"]}"? (YES or NO)\n
            Write out in a step by step manner your reasoning to be sure that your conclusion is correct.
            Give the reason as a string, not a list.
            {self.json_parser.get_format_instructions()}
            """
            ),
        }

        return [HumanMessage(content=[message])]


class AnswerCorrectnessEvaluator(BaseEvaluator):
    """
    答案正确性评估器（GPT-4V版本）。
    
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
        model: GPT-4V模型实例
    """
    def __init__(self, user_query: str, generated_answer: str, reference_answer: str, model):
        """
        初始化答案正确性评估器。
        
        :param user_query: 用户问题
        :param generated_answer: RAG系统生成的答案
        :param reference_answer: 标准答案
        :param model: GPT-4V模型实例
        """
        super().__init__(model=model, user_query=user_query, reference_answer=reference_answer,
                         generated_answer=generated_answer)

    def get_prompt(self, inputs: dict):
        """
        构建答案正确性评估提示词。
        
        采用教师批改学生答案的角色扮演方式，
        使评估更加准确和可解释。
        
        :param inputs: 包含user_query、generated_answer和reference_answer的字典
        
        :return: HumanMessage列表
        """
        message = {
            "type": "text",
            "text": (
                f"""
                You are given a question, the correct reference answer, and the student\'s answer. \
                You are asked to grade the student\'s answer as either correct or incorrect, based on the reference answer. \
                Ignore differences in punctuation and phrasing between the student answer and true answer. \
                It is OK if the student answer contains more information than the true answer, as long as it does not contain any conflicting statements.\
                USER QUERY: "{inputs["user_query"]}"\n\
                REFERENCE ANSWER: "{inputs["reference_answer"]}"\n\
                STUDENT ANSWER: "{inputs["generated_answer"]}"\n\
                answer_correctness: Is the student's answer correct? (YES or NO)\n
                Write out in a step by step manner your reasoning to be sure that your conclusion is correct.
                Give the reason as a string, not a list.
                {self.json_parser.get_format_instructions()}
                """
            ),
        }

        return [HumanMessage(content=[message])]


class ImageFaithfulnessEvaluator(BaseEvaluator):
    """
    图像忠实度评估器（GPT-4V版本）。
    
    评估生成的答案是否与检索到的图像内容事实一致，即答案中的
    信息是否能够从图像中得到支持，不存在与图像矛盾的内容。
    
    评估标准：
    - YES: 答案内容与图像一致，没有虚构信息
    - NO: 答案包含图像中不存在或矛盾的信息
    
    这是检测幻觉（hallucination）的重要指标。
    
    属性:
        user_query: 用户问题
        generated_answer: RAG系统生成的答案
        image: 检索到的图像（base64编码列表）
        model: GPT-4V模型实例
    """
    def __init__(self, user_query: str, generated_answer: str, image: str, model):
        """
        初始化图像忠实度评估器。
        
        :param user_query: 用户问题
        :param generated_answer: RAG系统生成的答案
        :param image: 图像的base64编码字符串
        :param model: GPT-4V模型实例
        """
        super().__init__(user_query=user_query, generated_answer=generated_answer, image=[image], model=model)

    def get_prompt(self, inputs: dict):
        """
        构建图像忠实度评估提示词。
        
        该方法构建包含图像和文本的多模态消息，
        评估答案与图像是否事实一致。
        
        :param inputs: 包含generated_answer和image列表的字典
        
        :return: HumanMessage列表，包含图像和评估提示词
        """
        if not inputs["image"]:
            return None

        messages = []
        for image in inputs['image']:
            image_message = {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image}"},
            }
            messages.append(image_message)

        text_message = {
            "type": "text",
            "text": (
                f"""
                Evaluate the following metric:\n
                image_faithfulness: Is the answer faithful to the context provided by the image(s), i.e. does it factually align with the context? (YES or NO)\n
                ANSWER: "{inputs["generated_answer"]}"\n\
                Write out in a step by step manner your reasoning to be sure that your conclusion is correct.
                Give the reason as a string, not a list.
                {self.json_parser.get_format_instructions()}
                """
            ),
        }

        messages.append(text_message)
        return [HumanMessage(content=messages)]


class TextFaithfulnessEvaluator(BaseEvaluator):
    """
    文本忠实度评估器（GPT-4V版本）。
    
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
        model: GPT-4V模型实例
    """
    def __init__(self, user_query: str, generated_answer: str, context: str, model):
        """
        初始化文本忠实度评估器。
        
        :param user_query: 用户问题
        :param generated_answer: RAG系统生成的答案
        :param context: 文本上下文
        :param model: GPT-4V模型实例
        """
        super().__init__(user_query=user_query, generated_answer=generated_answer, context=context, model=model)

    def get_prompt(self, inputs: dict):
        """
        构建文本忠实度评估提示词。
        
        该方法构建评估答案与文本是否事实一致的提示词，
        重点检查答案是否忠实于文本内容，是否存在幻觉。
        
        :param inputs: 包含generated_answer和context的字典
        
        :return: HumanMessage列表
        """
        if not inputs["context"]:
            return None
        
        message = {
            "type": "text",
            "text": (
                f"""
                Evaluate the following metric:\n
                text_faithfulness: Is the answer faithful to the context provided by the text, i.e. does it factually align with the context? (YES or NO)\n
                ANSWER: "{inputs["generated_answer"]}"\n\
                TEXT: "{inputs["context"]}"\n\
                Write out in a step by step manner your reasoning to be sure that your conclusion is correct.
                Give the reason as a string, not a list.
                {self.json_parser.get_format_instructions()}
                """
            ),
        }

        return [HumanMessage(content=[message])]
