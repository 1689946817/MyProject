"""
评估器接口模块

本模块定义了LLM评估器的抽象接口，为所有评估器类提供统一的规范。
采用抽象基类（ABC）模式，确保所有评估器都实现必要的方法。

接口设计遵循依赖倒置原则：
- 高层模块（EvaluationModule）依赖抽象接口
- 低层模块（具体评估器）实现抽象接口

主要组件：
- EvaluatorInterface: 评估器抽象基类，定义评估器的标准接口

作者: [项目作者]
日期: [创建日期]
"""

from abc import ABC, abstractmethod


class EvaluatorInterface(ABC):
    """
    LLM评估器抽象基类。
    
    该类定义了所有评估器必须实现的接口方法，作为评估器家族的统一规范。
    任何继承此类的评估器都必须实现run_evaluation和get_prompt方法。
    
    设计模式：
    - 接口模式：定义评估器的标准行为契约
    - 抽象工厂模式：为创建不同类型的评估器提供统一接口
    
    使用场景：
    当需要创建新的评估器时，应继承此接口并实现所有抽象方法。
    这确保了所有评估器具有一致的行为，便于在评估模块中统一调用。
    
    子类实现示例:
        >>> class MyEvaluator(EvaluatorInterface):
        ...     def run_evaluation(self) -> dict:
        ...         return {'grade': 1, 'reason': '评估通过'}
        ...     
        ...     def get_prompt(self, inputs: dict):
        ...         return f"Evaluate: {inputs['query']}"
    """

    @abstractmethod
    def run_evaluation(self) -> dict:
        """
        执行评估并返回结果。
        
        该方法是评估器的核心功能，负责执行完整的评估流程
        并返回包含评分和原因的结果字典。
        
        :return: 评估结果字典，必须包含以下键：
                 - grade: 评分（0或1的整数）
                 - reason: 评分原因（字符串）
        
        返回值示例:
            {
                'grade': 1,
                'reason': '答案与问题高度相关，准确回应了用户意图'
            }
        
        注意:
            子类实现时应确保返回格式的一致性，
            以便上层模块能够统一处理评估结果。
        """
        pass

    @abstractmethod
    def get_prompt(self, inputs: dict):
        """
        构建评估提示词。
        
        该方法负责根据输入参数构建发送给LLM的评估提示词。
        不同的评估指标需要不同的提示词模板和输入参数。
        
        :param inputs: 包含评估所需参数的字典，可能包含：
                      - user_query: 用户问题
                      - generated_answer: RAG系统生成的答案
                      - reference_answer: 标准答案（ground truth）
                      - context: 检索到的文本上下文
                      - image: 检索到的图像数据
        
        :return: 构建好的评估提示词，格式取决于具体实现：
                 - 对于GPT-4V: 通常返回HumanMessage列表
                 - 对于LLaVA: 通常返回包含prompt和image的字典
        
        提示词设计原则:
            1. 明确说明评估任务和指标定义
            2. 提供必要的上下文信息
            3. 指定输出格式要求（如JSON格式）
            4. 确保提示词清晰、无歧义
        """
        pass
