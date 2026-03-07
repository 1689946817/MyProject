"""
RAG评估模块

本模块实现了基于大语言模型的RAG系统评估功能，采用LLM-as-a-Judge方法，
通过GPT-4V或LLaVA等视觉语言模型对RAG系统的输出进行多维度评估。

支持的评估模型：
- GPT-4V: OpenAI的视觉语言模型，通过Azure API调用
- LLaVA: 开源的视觉语言模型，本地部署

支持的评估指标：
- Answer Correctness: 答案正确性
- Answer Relevancy: 答案相关性
- Text Faithfulness: 文本忠实度
- Image Faithfulness: 图像忠实度
- Text Context Relevancy: 文本上下文相关性
- Image Context Relevancy: 图像上下文相关性

作者: [项目作者]
日期: [创建日期]
"""

import base64
import importlib
import os
from typing import Dict, List
from langchain_openai import AzureChatOpenAI
from utils.azure_config import get_azure_config
from utils.model_loading_and_prompting.llava import load_llava_model

  
class EvaluationModule:
    """
    RAG管道评估模块的核心类。
    
    该类负责协调评估流程，根据选择的评估模型（GPT-4V或LLaVA）
    动态加载相应的评估器，并对RAG系统的输出进行多指标评估。
    
    属性:
        model_type (str): 评估模型类型，可选 'gpt4_vision' 或 'llava'
        model: 评估模型实例（AzureChatOpenAI 或 LlavaNextForConditionalGeneration）
        tokenizer: 分词器实例（仅LLaVA需要，GPT-4V为None）
        evaluator_module: 动态导入的评估器模块
        _metrics (dict): 支持的评估指标及其配置
    
    使用示例:
        >>> evaluator = EvaluationModule("llava")
        >>> results = evaluator.evaluate(
        ...     metrics=['Answer Correctness', 'Answer Relevancy'],
        ...     query="What is the motor voltage?",
        ...     generated_answer="The motor operates at 220V.",
        ...     reference_answer="220V",
        ...     context="The motor operates at 220V...",
        ...     image="base64_encoded_image"
        ... )
    """
    
    def __init__(self, model_type: str):
        """
        初始化评估模块。
        
        根据指定的模型类型加载相应的模型和评估器模块。
        对于GPT-4V，通过Azure API调用；对于LLaVA，加载本地模型。
        
        :param model_type: 评估模型类型，可选值：
                          - 'gpt4_vision': 使用GPT-4V模型
                          - 'llava': 使用LLaVA模型
        """
        self.model_type = model_type
          
        if model_type == "gpt4_vision":
            self.config = get_azure_config()
            gpt4v_config = self.config['gpt4_vision']
            self.model = AzureChatOpenAI(
                openai_api_version=gpt4v_config["openai_api_version"],
                azure_endpoint=gpt4v_config["openai_endpoint"],
                azure_deployment=gpt4v_config["deployment_name"],
                model=gpt4v_config["model_version"],
                api_key=os.environ.get("GPT4V_API_KEY"),
                max_tokens=500
            )
            self.tokenizer=None
            evaluator_module_name = "openai"
        
        else:
            self.model, self.tokenizer = load_llava_model("llava-hf/llava-v1.6-mistral-7b-hf")
            evaluator_module_name = 'llava'
          
        self.evaluator_module = self._import_evaluator_module(evaluator_module_name)

        self._metrics = {
            'Answer Relevancy': {
                'eval_method': self._evaluate_answer_relevancy,
                'required_args': ['query', 'generated_answer']
            },
            'Answer Correctness': {
                'eval_method': self._evaluate_answer_correctness,
                'required_args': ['query', 'generated_answer', 'reference_answer']
            },
            'Image Faithfulness': {
                'eval_method': self._evaluate_image_faithfulness,
                'required_args': ['query', 'generated_answer', 'image']
            },
            'Text Faithfulness': {
                'eval_method': self._evaluate_text_faithfulness,
                'required_args': ['query', 'generated_answer', 'context']
            },
            'Image Context Relevancy': {
                'eval_method': self._evaluate_image_context_relevancy,
                'required_args': ['query', 'image']
            },
            'Text Context Relevancy': {
                'eval_method': self._evaluate_text_context_relevancy,
                'required_args': ['query', 'context']
            }
        }
        
    def _import_evaluator_module(self, model_type: str):  
        """
        动态导入评估器模块。
        
        根据模型类型动态导入对应的评估器实现模块，
        这样可以在运行时决定使用哪个评估器，而不需要在代码中硬编码。
        
        :param model_type: 模型类型，用于确定要导入的模块名称
        :return: 导入的评估器模块对象
        """
        module_name = f'evaluation.evaluators.evaluators_{model_type}'   
        evaluator_module = importlib.import_module(module_name)  
        return evaluator_module  
  
    def create_evaluator_instance(self, evaluator_class_name: str, **kwargs):  
        """
        动态创建评估器实例。
        
        从动态导入的模块中获取评估器类，并根据模型类型
        传入相应的参数创建评估器实例。
        
        :param evaluator_class_name: 评估器类名，如 'AnswerRelevancyEvaluator'
        :param kwargs: 传递给评估器构造函数的参数
        
        :return: 评估器实例
        
        示例:
            >>> evaluator = self.create_evaluator_instance(
            ...     'AnswerRelevancyEvaluator',
            ...     user_query="What is X?",
            ...     generated_answer="X is Y."
            ... )
        """
        evaluator_class = getattr(self.evaluator_module, evaluator_class_name)  
        if self.tokenizer:
            evaluator_instance = evaluator_class(model=self.model, tokenizer=self.tokenizer, **kwargs)
        else:
            evaluator_instance = evaluator_class(model=self.model, **kwargs)
        return evaluator_instance  
  

    def _evaluate_answer_relevancy(self, query: str, generated_answer: str) -> dict:  
        """
        评估答案相关性。
        
        判断生成的答案是否与用户问题相关，即答案是否
        能够回应用户的问题意图。
        
        :param query: 用户问题
        :param generated_answer: RAG系统生成的答案
        
        :return: 包含评估结果的字典，格式为 {'Answer Relevancy': {'grade': 0/1, 'reason': '...'}}
        """
        evaluator = self.create_evaluator_instance('AnswerRelevancyEvaluator', user_query=query, generated_answer=generated_answer)  
        return {'Answer Relevancy': evaluator.run_evaluation()}

    def _evaluate_answer_correctness(self, query: str, generated_answer: str, reference_answer: str) -> dict:
        """
        评估答案正确性。
        
        将生成的答案与标准答案（ground truth）进行对比，
        判断生成答案是否正确。
        
        :param query: 用户问题
        :param generated_answer: RAG系统生成的答案
        :param reference_answer: 标准答案
        
        :return: 包含评估结果的字典
        """
        evaluator = self.create_evaluator_instance('AnswerCorrectnessEvaluator', user_query=query, generated_answer=generated_answer, reference_answer=reference_answer)
        return {'Answer Correctness': evaluator.run_evaluation()}
    
    def _evaluate_image_faithfulness(self, query: str, generated_answer: str, image: str) -> dict:
        """
        评估图像忠实度。
        
        判断生成的答案是否与检索到的图像内容事实一致，
        即答案中的信息是否能够从图像中得到支持。
        
        :param query: 用户问题
        :param generated_answer: RAG系统生成的答案
        :param image: 检索到的图像（base64编码）
        
        :return: 包含评估结果的字典
        """
        evaluator = self.create_evaluator_instance('ImageFaithfulnessEvaluator', user_query=query, generated_answer=generated_answer, image=image)
        return {'Image Faithfulness': evaluator.run_evaluation()}
    
    def _evaluate_text_faithfulness(self, query: str, generated_answer: str, context: str) -> dict:
        """
        评估文本忠实度。
        
        判断生成的答案是否与检索到的文本上下文事实一致，
        即答案中的信息是否能够从文本中得到支持，不存在幻觉。
        
        :param query: 用户问题
        :param generated_answer: RAG系统生成的答案
        :param context: 检索到的文本上下文
        
        :return: 包含评估结果的字典
        """
        evaluator = self.create_evaluator_instance('TextFaithfulnessEvaluator', user_query=query, generated_answer=generated_answer, context=context)
        return {'Text Faithfulness': evaluator.run_evaluation()}
    
    def _evaluate_image_context_relevancy(self, query: str, image: str) -> dict:
        """
        评估图像上下文相关性。
        
        判断检索到的图像是否与用户问题相关，
        即图像是否能够帮助回答用户的问题。
        
        :param query: 用户问题
        :param image: 检索到的图像（base64编码）
        
        :return: 包含评估结果的字典
        """
        evaluator = self.create_evaluator_instance('ImageContextRelevancyEvaluator', user_query=query, image=image)
        return {'Image Context Relevancy': evaluator.run_evaluation()}

    def _evaluate_text_context_relevancy(self, query: str, context: str) -> dict:
        """
        评估文本上下文相关性。
        
        判断检索到的文本是否与用户问题相关，
        即文本是否包含能够回答用户问题的信息。
        
        :param query: 用户问题
        :param context: 检索到的文本上下文
        
        :return: 包含评估结果的字典
        """
        evaluator = self.create_evaluator_instance('TextContextRelevancyEvaluator', user_query=query, context=context)
        return {'Text Context Relevancy': evaluator.run_evaluation()}


    def evaluate(self, metrics: List[str], **kwargs) -> Dict[str, dict]:
        """
        执行多指标评估。
        
        根据指定的评估指标列表，对RAG系统的输出进行评估。
        每个指标需要特定的输入参数，函数会自动检查参数完整性。
        
        :param metrics: 要评估的指标列表，如 ['Answer Correctness', 'Answer Relevancy']
        
        关键字参数:
            query (str): 用户问题
            generated_answer (str): RAG系统生成的答案
            reference_answer (str): 标准答案（ground truth）
            context (str): 检索到的文本上下文
            image (str): 检索到的图像（base64编码）
        
        :return: 评估结果字典，格式为：
                 {
                     'Answer Correctness': {'grade': 0/1, 'reason': '...'},
                     'Answer Relevancy': {'grade': 0/1, 'reason': '...'},
                     ...
                 }
        
        :raises ValueError: 当缺少必要参数或指定了无效的评估指标时抛出
        
        示例:
            >>> results = evaluation_module.evaluate(
            ...     metrics=['Answer Correctness', 'Text Faithfulness'],
            ...     query="What is the voltage?",
            ...     generated_answer="220V",
            ...     reference_answer="220V",
            ...     context="The motor operates at 220V..."
            ... )
        """
        results = {}
        for metric in metrics:
            if metric in self._metrics:
                required_args = self._metrics[metric]['required_args']
                if self._check_required_arguments(required_args, metric, list(kwargs.keys())):
                    metric_kwargs = {arg: kwargs[arg] for arg in required_args}
                    results.update(self._metrics[metric]['eval_method'](**metric_kwargs))
            else:
                raise ValueError(f"Invalid metric '{metric}'\n"
                                 f"Valid metrics: {list(self._metrics.keys())}")
        return results

    def _check_required_arguments(self, required_args: List[str], metric: str, kwargs: List[str]) -> bool:
        """
        检查评估指标所需的参数是否完整。
        
        在执行评估前，验证所有必要的参数是否已提供。
        如果缺少参数，抛出ValueError异常并指出缺失的参数。
        
        :param required_args: 该评估指标所需的参数列表
        :param metric: 评估指标名称
        :param kwargs: 实际提供的参数键列表
        
        :return: 如果所有必要参数都已提供，返回True
        
        :raises ValueError: 当缺少必要参数时抛出，包含详细的缺失参数信息
        """
        missing_args = [arg for arg in required_args if arg not in kwargs]
        if missing_args:
            raise ValueError(f"Missing required arguments for metric '{metric}':\n"
                             f"Required arguments: {self._metrics[metric]['required_args']}\n"
                             f"Missing: {', '.join(missing_args)}")
        return True


if __name__ == '__main__':
    """
    模块测试入口。
    
    演示如何使用EvaluationModule进行评估测试。
    """
    evaluator_model = "llava"
    evaluation_module = EvaluationModule(evaluator_model)

    user_query = "What is the transformer architecture?"
    context = """The dominant sequence transduction models are based on complex recurrent or convolutional neural
            networks in an encoder-decoder configuration. The best performing models also connect the encoder and decoder
            through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely
            on attention mechanisms, dispensing with recurrence and convolutions entirely. Experiments on two machine
            translation tasks show these models to be superior in quality while being more parallelizable and requiring
            significantly less time to train. Our model achieves 28.4 BLEU on the WMT 2014 English-to-German translation
            task, improving over the existing best results, including ensembles by over 2 BLEU. On the WMT 2014
            English-to-French translation task, our model establishes a new single-model state-of-the-art BLEU score of
            41.8 after training for 3.5 days on eight GPUs, a small fraction of the training costs of the best models from
            the literature. We show that the Transformer generalizes well to other tasks by applying it successfully to
            English constituency parsing both with large and limited training data."""

    img_path = "./img/transformer.PNG"
    with open(img_path, "rb") as image_file:
        image = base64.b64encode(image_file.read()).decode("utf-8")

    reference_answer = """The transformer architecture is a popular deep learning model used in natural language
    processing tasks. It replaces recurrent neural networks with a self-attention mechanism, allowing the model to
    capture long-range dependencies more effectively. It consists of an encoder and decoder, each with multiple layers.
    The transformer has achieved state-of-the-art performance in NLP and serves as the basis for models like BERT, GPT,
    and T5."""
    generated_answer = "I love cats"
    
    METRICS = ['Answer Correctness', 'Answer Relevancy','Image Faithfulness',
               'Image Context Relevancy','Text Faithfulness', 'Text Context Relevancy']
    
    results = evaluation_module.evaluate(metrics=METRICS,
                                         query=user_query,
                                         context=context,
                                         image=image,
                                         generated_answer=generated_answer,
                                         reference_answer=reference_answer)
    
    print(results)
