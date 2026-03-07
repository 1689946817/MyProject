"""
RAG管道评估脚本

本模块实现了对RAG（检索增强生成）系统输出的自动化评估功能。
使用LLM-as-a-Judge方法，通过大语言模型对RAG系统的生成答案进行多维度评估。

评估指标包括：
- Answer Correctness: 答案正确性，评估生成答案与参考答案的一致性
- Answer Relevancy: 答案相关性，评估生成答案与用户问题的相关性
- Image Faithfulness: 图像忠实度，评估生成答案与检索图像的事实一致性
- Text Faithfulness: 文本忠实度，评估生成答案与检索文本的事实一致性
- Image Context Relevancy: 图像上下文相关性，评估检索图像与用户问题的相关性
- Text Context Relevancy: 文本上下文相关性，评估检索文本与用户问题的相关性

作者: [项目作者]
日期: [创建日期]
"""

import os
import pandas as pd
from typing import List
from evaluation_module import EvaluationModule


AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")

METRICS = ['Answer Correctness', 'Answer Relevancy']
IMAGE_METRICS = ['Image Faithfulness', 'Image Context Relevancy']
TEXT_METRICS = ['Text Faithfulness', 'Text Context Relevancy']
AGGREGATED_METRICS = ['Faithfulness', 'Context Relevancy']



def evaluate_row(metrics: List[str], index: int, context: str, image: str, user_query: str, generated_answer: str,
                 reference_answer: str, evaluator: str, scores_df: pd.DataFrame) -> pd.DataFrame:
    """
    评估RAG系统的单个输出结果。
    
    该函数调用评估模块对单个查询的生成结果进行多指标评估，
    并将评估结果（评分和原因）存储到结果数据框中。
    
    :param metrics: 要评估的指标列表，如 ['Answer Correctness', 'Answer Relevancy']
    :param index: 数据框中当前行的索引，用于定位评估结果存储位置
    :param context: 检索系统检索到的文本上下文，作为生成答案的参考
    :param image: 检索系统检索到的图像的base64编码字符串
    :param user_query: RAG系统要回答的用户问题
    :param generated_answer: RAG系统针对用户问题生成的答案
    :param reference_answer: 用户查询的标准答案（ground truth）
    :param evaluator: 评估器实例，用于执行具体的评估任务
    :param scores_df: 用于存储评估结果的数据框
    
    :return: 包含当前行评估结果的数据框
    
    示例:
        >>> scores_df = evaluate_row(
        ...     metrics=['Answer Correctness'],
        ...     index=0,
        ...     context="The motor operates at 220V...",
        ...     image="base64_encoded_image_string",
        ...     user_query="What is the motor voltage?",
        ...     generated_answer="The motor operates at 220V.",
        ...     reference_answer="220V",
        ...     evaluator=evaluator_instance,
        ...     scores_df=pd.DataFrame()
        ... )
    """
    results = evaluator.evaluate(metrics=metrics,
                                query=user_query,
                                context=context,
                                image=image,
                                generated_answer=generated_answer,
                                reference_answer=reference_answer)
    print(results)
    for k, v in results.items():
        scores_df.at[index, f"{k} grade"] = v["grade"]
        scores_df.at[index, f"{k} reason"] = v["reason"]

    return scores_df


def handle_no_data(index, data_type: str, scores_df: pd.DataFrame) -> pd.DataFrame:
    """
    处理缺失数据的情况。
    
    当检索系统没有提供文本或图像作为上下文时，该函数将相关评估指标
    的评分设置为None，并记录缺失原因。这确保了评估结果数据框的完整性。
    
    :param index: 数据框中当前行的索引
    :param data_type: 缺失的数据类型，可选值为 "Text" 或 "Image"
    :param scores_df: 包含评估结果的数据框
    
    :return: 更新后的评估结果数据框
    
    示例:
        >>> scores_df = handle_no_data(index=0, data_type="Image", scores_df=scores_df)
        >>> print(scores_df.at[0, "Image Faithfulness grade"])  # None
        >>> print(scores_df.at[0, "Image Faithfulness reason"])  # "No Image provided"
    """
    scores_df.at[index, f"{data_type} Faithfulness grade"] = None
    scores_df.at[index, f"{data_type} Faithfulness reason"] = f"No {data_type} provided"
    scores_df.at[index, f"{data_type} Context Relevancy grade"] = None
    scores_df.at[index, f"{data_type} Context Relevancy reason"] = f"No {data_type} provided"
    return scores_df


def evaluate_dataframe(input_df: pd.DataFrame, evaluator: str, output_file: str) -> pd.DataFrame:
    """
    批量评估RAG系统的输出结果。
    
    该函数遍历输入数据框中的每一行，对每个查询的生成结果进行评估，
    包括答案正确性、相关性、忠实度和上下文相关性等指标。
    评估结果会实时保存到指定的JSON文件中。
    
    评估流程：
    1. 遍历数据框中的每个查询
    2. 提取查询相关信息（问题、答案、上下文等）
    3. 根据上下文类型确定评估指标
    4. 执行评估并记录结果
    5. 计算聚合指标（整体忠实度和上下文相关性）
    6. 保存评估结果
    
    :param input_df: 包含RAG系统输出的数据框，必须包含以下列：
                     - user_query: 用户问题
                     - reference_answer: 标准答案
                     - generated_answer: 生成的答案
                     - context: 检索的文本上下文
                     - image: 检索的图像（base64编码列表）
    :param evaluator: 评估器实例（EvaluationModule）
    :param output_file: 评估结果保存的JSON文件路径
    
    :return: 包含所有评估结果的数据框
    
    示例:
        >>> input_df = pd.read_json("rag_output.json")
        >>> evaluator = EvaluationModule("llava")
        >>> scores_df = evaluate_dataframe(input_df, evaluator, "evaluation_results.json")
    """
    scores_df = pd.DataFrame()
    
    for index, row in input_df.iterrows():
        print(f"Evaluating query no. {index+1}...")
        
        user_query = input_df["user_query"][index]
        reference_answer = input_df["reference_answer"][index]
        generated_answer = input_df["generated_answer"][index]
        context = input_df["context"][index]
        image = input_df["image"][index][0] if input_df["image"][index] else []
        
        metrics = METRICS.copy()
        if not image:
            scores_df = handle_no_data(index, "Image", scores_df)
        else:
            metrics.extend(IMAGE_METRICS)
        if not context:
            scores_df = handle_no_data(index, "Text", scores_df)
        else:
            metrics.extend(TEXT_METRICS)
        
        scores_df = evaluate_row(metrics, index, context, image, user_query, generated_answer, reference_answer, evaluator, scores_df)
                
        for metric in AGGREGATED_METRICS:
            img_metric = scores_df.at[index, f"Image {metric} grade"]
            text_metric = scores_df.at[index, f"Text {metric} grade"]
            
            df_tmp = pd.DataFrame()
            df_tmp[metric] = [img_metric, text_metric]
            
            grade = df_tmp[metric].mean()
            scores_df.at[index, f"{metric} grade"] = grade
        
        scores_df.to_json(output_file, orient="records", indent=2)
    
    return scores_df
  
  
def calculate_and_print_averages(scores_df: pd.DataFrame):
    """
    计算并打印所有评估指标的平均分数。
    
    该函数遍历所有评估指标，计算每个指标在整个数据集上的平均分数，
    并将结果打印到控制台。这有助于了解RAG系统的整体性能表现。
    
    :param scores_df: 包含评估结果的数据框，每列对应一个评估指标的评分
    
    示例输出:
        Answer correctness: 0.85
        Answer relevancy: 0.90
        Image faithfulness: 0.78
        ...
    """
    average_dict = {}
    for grade in METRICS + IMAGE_METRICS + TEXT_METRICS + AGGREGATED_METRICS:
        average_dict[grade] = scores_df[f'{grade} grade'].mean()
        print(f"{grade.capitalize()}: {average_dict[grade]}")
        


if __name__ == "__main__":
    """
    主函数入口：执行RAG管道评估流程。
    
    使用方法：
    1. 设置生成模型和评估模型
    2. 指定RAG输出文件路径
    3. 创建评估模块实例
    4. 执行评估并输出结果
    """
    generator_model = "llava"
    evaluator_model = "llava"

    rag_output_file = rf"../../sample_data/rag_outputs/rag_output_img_summaries_{generator_model}.json"
    evaluation_output_file = rf"../../sample_data/rag_evaluation_results/evaluation_{generator_model}_generator_{evaluator_model}_evaluator.json"

    evaluator = EvaluationModule(evaluator_model)

    input_df = pd.read_json(rag_output_file)
    scores_df = evaluate_dataframe(input_df, evaluator, evaluation_output_file)
    calculate_and_print_averages(scores_df)
