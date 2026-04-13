# 检索器实验分析报告

## 1. 数据范围
- COCO 总体结果：3 个方法
- UniDoc 分领域结果：27 条方法-领域记录

## 2. 总体结论
- COCO 上 MRR 最优方法为 `baseline_clip`，MRR=0.9667，Recall@1=0.9500。
- COCO 上最弱方法为 `baseline_ocr`，MRR=0.0293。
- UniDoc 分领域平均指标显示 `baseline_clip` 的平均 MRR 最高，为 0.9544。

## 3. 结果解读
- COCO 更偏视觉描述对齐，`baseline_clip` 在首位命中和排序指标上通常更强。
- UniDoc 的分领域图更适合论文主文，用于突出方法在专业文档场景下的泛化性。
- OCR 基线建议同时保留完整版本与去 OCR 版本，以兼顾对照充分性和主图可读性。

## 4. 图表清单
- `retrieval_coco_metrics_with_ocr`
- `retrieval_coco_metrics_without_ocr`
- `retrieval_latency_with_ocr`
- `retrieval_latency_without_ocr`
- `retrieval_domain_metrics_with_ocr`
- `retrieval_domain_metrics_without_ocr`
- `retrieval_heatmap_with_ocr`
- `retrieval_heatmap_without_ocr`
- `retrieval_first_hit_distribution_with_ocr`
- `retrieval_first_hit_distribution_without_ocr`
    