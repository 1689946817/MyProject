"""
评估器基类模块

本模块定义了LLM评估器的基类实现，为具体的评估器提供通用的评估流程和工具方法。
支持GPT-4V和LLaVA两种评估模型，实现了评估链的构建和结果解析。

主要组件：
- EvaluationResult: 评估结果的数据模型，包含评分和原因
- BaseEvaluator: 评估器基类，提供评估流程的通用实现

评估流程：
1. 构建评估提示词（由子类实现）
2. 调用LLM模型进行评估
3. 解析JSON格式的评估结果
4. 将评分转换为数值（0或1）

作者: [项目作者]
日期: [创建日期]
"""

import os
from abc import abstractmethod
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from transformers import LlavaNextForConditionalGeneration
from evaluation.evaluators.evaluator_interface import EvaluatorInterface
from utils.model_loading_and_prompting.llava import llava_call


class EvaluationResult(BaseModel):
    """
    评估结果数据模型。
    
    使用Pydantic定义评估结果的结构，确保输出格式的规范性。
    每个评估结果包含两个必填字段：评分和评分原因。
    
    属性:
        grade: 评估评分，取值为 "YES" 或 "NO"
        reason: 评分原因的详细解释说明
    
    示例:
        >>> result = EvaluationResult(grade="YES", reason="答案与问题高度相关")
        >>> result.dict()
        {'grade': 'YES', 'reason': '答案与问题高度相关'}
    """
    grade: str = Field(description="the grade after evaluating the metric (YES or NO)")
    reason: str = Field(description="The reasoning behind the grading decision")


class BaseEvaluator(EvaluatorInterface):
    """
    LLM评估器基类。
    
    该类实现了评估器的通用逻辑，包括评估链的构建、结果解析和格式修正。
    子类只需实现get_prompt方法来定义特定指标的评估提示词。
    
    设计模式：
    - 模板方法模式：run_evaluation定义评估流程骨架，get_prompt由子类实现
    - 策略模式：支持不同的评估模型（GPT-4V和LLaVA）
    
    属性:
        model: 评估模型实例（AzureChatOpenAI或LlavaNextForConditionalGeneration）
        tokenizer: 分词器实例（仅LLaVA需要，GPT-4V为None）
        model_type: 模型类型，用于区分评估链的构建方式
        json_parser: JSON输出解析器，用于解析评估结果
        check_grade_chain: 评分转换链，将YES/NO转换为1/0
        kwargs: 评估所需的其他参数（如用户问题、生成答案等）
    
    使用示例:
        >>> class MyEvaluator(BaseEvaluator):
        ...     def get_prompt(self, inputs):
        ...         return {"prompt": f"Evaluate: {inputs['query']}"}
        >>> 
        >>> evaluator = MyEvaluator(model=gpt4v_model, user_query="What is X?")
        >>> result = evaluator.run_evaluation()
    """
    def __init__(self, tokenizer=None, **kwargs):
        """
        初始化评估器基类。

        模型通过环境变量自动构造，无需外部传入：
        - EVAL_BASE_URL: API端点（默认 https://api.openai.com/v1）
        - EVAL_API_KEY: API密钥
        - EVAL_MODEL: 模型名称（默认 gpt-4o）

        :param tokenizer: 分词器实例，可选。提供时使用LLaVA，否则使用OpenAI兼容模型

        关键字参数:
            user_query (str): 用户问题
            generated_answer (str): RAG系统生成的答案
            reference_answer (str): 标准答案（ground truth）
            context (str): 检索到的文本上下文
            image (str): 检索到的图像（base64编码）
        """
        self.model = ChatOpenAI(
            base_url=os.environ.get("EVAL_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.environ.get("EVAL_API_KEY"),
            model=os.environ.get("EVAL_MODEL", "gpt-4o"),
            max_tokens=int(os.environ.get("EVAL_MAX_TOKENS", "1000")),
            temperature=0,
        )
        self.model_type = ChatOpenAI
        self.json_parser = JsonOutputParser(pydantic_object=EvaluationResult)
        self.kwargs = kwargs
        self.check_grade_chain = RunnableLambda(self.get_numeric_score)

        if tokenizer:
            self.tokenizer = tokenizer
        else:
            self.tokenizer = None
            
            
    def call_llava(self, inputs: dict) -> str:
        """
        调用LLaVA模型进行推理。
        
        该方法封装了LLaVA模型的调用逻辑，将提示词和图像
        传递给模型并返回生成的文本结果。
        
        :param inputs: 包含prompt和可选image的字典
                      - prompt: 评估提示词
                      - image: PIL Image对象（可选）
        
        :return: LLaVA模型生成的文本响应
        
        示例:
            >>> inputs = {"prompt": "[INST] Evaluate... [/INST]", "image": pil_image}
            >>> response = self.call_llava(inputs)
        """
        prompt = inputs['prompt']
        image = inputs.get('image', None)
        ans = llava_call(prompt, self.model, self.tokenizer, device="cuda", image=image)
        return ans
        

    def get_numeric_score(self, inputs: str) -> dict:
        """
        将评分转换为数值。
        
        该方法将LLM输出的评分（YES或NO）转换为数值（1或0），
        便于后续的统计分析和比较。
        
        :param inputs: 包含grade和reason的字典
        
        :return: 更新后的字典，grade字段转换为数值

        示例:
            >>> inputs = {"grade": "YES", "reason": "答案正确"}
            >>> result = self.get_numeric_score(inputs)
            >>> print(result["grade"])  # 1
        """
        inputs["grade"] = 1 if inputs["grade"].upper() == "YES" else 0
        return inputs

    def run_evaluation(self) -> dict:
        """
        执行评估流程。
        
        该方法构建完整的评估链并执行评估，流程如下：
        1. 调用get_prompt构建评估提示词（由子类实现）
        2. 调用LLM模型生成评估结果
        3. 解析JSON格式的输出
        4. 修正可能的格式错误（仅LLaVA）
        5. 将评分转换为数值
        
        对于LLaVA模型，使用fix_format_parser来修正可能的JSON格式错误，
        因为开源模型的输出格式可能不够稳定。
        
        对于GPT-4V模型，直接使用json_parser解析，因为GPT-4V的输出格式更规范。
        
        :return: 评估结果字典，包含：
                 - grade: 评分（0或1）
                 - reason: 评分原因（字符串）
        
        示例:
            >>> evaluator = AnswerRelevancyEvaluator(
            ...     model=gpt4v_model,
            ...     user_query="What is X?",
            ...     generated_answer="X is Y."
            ... )
            >>> result = evaluator.run_evaluation()
            >>> print(result)  # {'grade': 1, 'reason': '答案直接回应了问题'}
        """ 
        if self.tokenizer:
            chain = RunnableLambda(self.get_prompt) | RunnableLambda(self.call_llava) | self.fix_format_parser | self.check_grade_chain
        else:
            chain = RunnableLambda(self.get_prompt) | self.model | self.json_parser | self.check_grade_chain
        result = chain.invoke(self.kwargs)

        return result

    @abstractmethod
    def get_prompt(self, inputs: dict):
        """
        构建评估提示词（抽象方法）。
        
        该方法由子类实现，用于构建特定评估指标的提示词。
        不同的评估指标需要不同的提示词模板和输入参数。
        
        :param inputs: 包含评估所需参数的字典，如：
                      - user_query: 用户问题
                      - generated_answer: 生成的答案
                      - reference_answer: 标准答案
                      - context: 文本上下文
                      - image: 图像数据
        
        :return: 评估提示词，格式取决于评估模型：
                 - GPT-4V: 返回HumanMessage列表
                 - LLaVA: 返回包含prompt和image的字典
        
        子类实现示例:
            >>> def get_prompt(self, inputs: dict):
            ...     prompt = f"Evaluate: {inputs['user_query']}"
            ...     return {"prompt": prompt}
        """
        pass
