import json
import csv
import base64
import os
from openai import OpenAI
from tqdm import tqdm

# ================= 配置区 =================
client = OpenAI(
    api_key="sk-1fce3abb190e45a29a15aadb4a67390e", 
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1" 
)

INPUT_JSONL = 'val_eval_results.jsonl'
OUTPUT_CSV = 'evaluation_report_qwen3.5-plus.csv'
# INPUT_JSONL = 'e:\\BiShe\\Code2\\MyProject\\finetune\\val_eval_results.jsonl'
# OUTPUT_CSV = 'e:\\BiShe\\Code2\\MyProject\\finetune\\evaluation_report_qwen3.5-plus.csv'
JUDGE_MODEL = "qwen3.5-plus"

# 完整的系统提示词，让法官据此判断模型是否遵循了指令
ORIGINAL_SYSTEM_PROMPT = """你是一名多模态数据分析专家。请解析给定图像，并按照以下逻辑生成描述文本。要求：不要输出任何类似 "属性名:" 或 "JSON标签" 的固定格式，统一使用 [###] 作为不同部分的唯一分隔符。生成逻辑如下：[第一部分：定义分类] 开头必须明确指出该图片的类型（这部分可以稍微详细些，例如：它是某某机器的操作流程图、历史地图、职场截图、自然风景、工程逻辑图、手绘草图等）。[第二部分：语义摘要] 紧接分类后，用一段话概括图像的核心意图和功能。[第三部分：视觉细节] 描述主体、空间关系、颜色及环境。[第四部分：文字提取] 罗列图中所有的关键文字信息。[第五部分：检索关键词] 提供 10 个有助于精准检索的词汇。示例格式：[###] 该图片是一份职场维权指南截图。主要内容是关于“裁员黄金一小时”的应对策略，用于帮助职场人士处理离职补偿问题。[###] 画面中心是手持的一张白色 A4 纸... [###] 标题为“被通知裁员的黄金一小时”... [###] 裁员, 维权, 劳动法, 补偿金 ..."""

JUDGE_INSTRUCTIONS = f"""你是一名资深的视觉语言评测专家。我会给你一张【原始图片】，以及三个模型产生的回答。
这三个模型在生成时都应遵循以下【系统指令】：
{ORIGINAL_SYSTEM_PROMPT}

请从以下三个维度打分（1-10分）：
1. 格式遵循度 (Format): 是否严格使用 [###] 分隔五个部分。
2. 文字准确性 (OCR): 提取的文字是否与图片内容一致。
3. 语义理解度 (Semantics): 分类和摘要是否精准深刻。

请仅返回 JSON 格式结果，不要有余赘文字：
{{
  "score_base": {{"format": 0, "ocr": 0, "semantics": 0}},
  "score_75": {{"format": 0, "ocr": 0, "semantics": 0}},
  "score_140": {{"format": 0, "ocr": 0, "semantics": 0}},
  "reason": "综合评价"
}}
"""
# ==========================================
def encode_image(image_path):
    #local_path = image_path.replace("/mnt/workspace/data/", "E:\\BiShe\\Code2\\MyProject\\data\\")
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')
# def encode_image(image_path):
#     with open(image_path, "rb") as image_file:
#         return base64.b64encode(image_file.read()).decode('utf-8')

def judge_item(item):
    base64_img = encode_image(item['image'])
    
    user_msg = [
        {
            "type": "text", 
            "text": f"参考真值: {item['ground_truth']}\n\n"
                    f"模型 A (原始): {item['res_base']}\n\n"
                    f"模型 B (Ckpt-75): {item['res_75']}\n\n"
                    f"模型 C (Ckpt-140): {item['res_140']}"
        },
        {
            "type": "image_url", 
            "image_url": {"url": f"data:image/png;base64,{base64_img}"}
        }
    ]

    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": JUDGE_INSTRUCTIONS},
            {"role": "user", "content": user_msg}
        ],
        response_format={ "type": "json_object" }
    )
    return json.loads(response.choices[0].message.content)

def main():
    scored_data = []
    with open(INPUT_JSONL, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for line in tqdm(lines, desc=f"{JUDGE_MODEL} 视觉打分中"):
        item = json.loads(line)
        try:
            res = judge_item(item)
            scored_data.append([
                item['id'],
                sum(res['score_base'].values())/3,
                sum(res['score_75'].values())/3,
                sum(res['score_140'].values())/3,
                res['reason']
            ])
        except Exception as e:
            print(f"样本 {item['id']} 评分失败: {e}")

    with open(OUTPUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Base_Avg", "Ckpt75_Avg", "Ckpt140_Avg", "Judge_Reason"])
        writer.writerows(scored_data)

    print(f"✅ 打分完成！结果已保存至: {OUTPUT_CSV}")

if __name__ == '__main__':
    main()