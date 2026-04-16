# 微调实验分析报告

## 1. 总体表现
- 三组模型平均分分别为：Base=7.457，Ckpt75=7.826，Ckpt140=7.971。
- 最优检查点为 `ckpt140`。
- 相比 Base，Ckpt75 平均提升 0.370，Ckpt140 平均提升 0.514。

## 2. 稳定性判断
- 优先建议使用 `Ckpt75` 作为论文中的最佳 checkpoint。
- `Ckpt140` 整体仍高于 Base，但样本级波动更大。
- 检测到 Ckpt140 对 Base 的显著退化样本数：1。

## 3. 训练过程
- 训练日志共解析出 36 条有效记录。
- 建议将学习曲线与最佳 checkpoint 结论结合描述。

## 4. 图表清单
- `finetune_overall_scores`
- `finetune_score_distribution`
- `finetune_score_delta_distribution`
- `finetune_wtl`
- `finetune_learning_curves`
