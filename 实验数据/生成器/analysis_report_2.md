# 生成器实验分析报告

## 1. 总体表现
- 答案正确性最高的方法为 `baseline_clip`，平均分为 0.8700。
- `proposed` 相比 `no_rag` 的答案正确性提升为 0.6200。
- `proposed` 的答案相关性为 100.0%，图像忠实度为 73.5%。

## 2. 结果解读
- `no_rag` 的相关性不低，但正确性很弱，说明无检索时容易生成表面相关的回答。
- `baseline_ocr` 在当前 UniDoc 实验中整体偏弱，适合作为弱基线。
- 主文建议突出 `proposed` 与 `baseline_clip` 的对比，并在附图保留 OCR 版本。

## 3. 图表清单
- `generation_overall_metrics_with_ocr`
- `generation_overall_metrics_without_ocr`
- `generation_domain_correctness_with_ocr`
- `generation_domain_correctness_without_ocr`
- `generation_qtype_correctness_with_ocr`
- `generation_qtype_correctness_without_ocr`
- `generation_relevancy_faithfulness_with_ocr`
- `generation_relevancy_faithfulness_without_ocr`
- `generation_improvement_with_ocr`
- `generation_improvement_without_ocr`
    