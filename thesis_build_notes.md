# 论文构建说明

## 当前中间产物

- `facts_inventory.md`
- `terminology_table.md`
- `compliance_checklist.md`
- `thesis_outline.md`
- `chapter_1_intro.md`
- `chapter_2_related_tech.md`
- `chapter_3_analysis.md`
- `chapter_4_design.md`
- `chapter_5_implementation.md`
- `chapter_6_experiments.md`
- `chapter_7_conclusion.md`
- `revision_log.md`
- `final_review_checklist.md`

## 当前构建状态

- 事实盘点完成。
- 七章 Markdown 草稿完成。
- 中文摘要、英文摘要、参考文献、致谢已补齐。
- 已基于学校模板生成最终 DOCX。
- 已完成一轮成品结构核验，确认摘要、Abstract、目录、正文、参考文献和致谢均存在。

## DOCX 处理策略

- 目标模板：`docs/东北大学本科生毕业设计（论文）模版.docx`
- 优先保留模板现有样式
- 已采用 Word COM 自动化方式进行填充，脚本为 `scripts/build_thesis_docx.py`

## 风险项

1. 参考文献目前已整理为可交付版本，但若导师要求完全沿用既有报告中的文献条目，仍可再做一次人工核对。
2. 当前正文以表格和文字说明为主，未额外插入新绘制图示，以避免编造不存在的系统截图或实验图。
3. 若后续需要进一步微调封面位置、目录缩进或页眉页脚，建议直接在生成的 DOCX 上做一次人工终审。
