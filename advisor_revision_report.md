# 导师式复核与修改报告

## 一、学校规范发现的问题

1. 英文关键词标签仍写为 `Key Words`，不符合当前英文摘要标签统一口径。
2. 参考文献虽然已达到学校建议下限，但其中 4 条为前端框架官方文档，学术支撑力度偏弱。
3. 摘要结尾仍偏“总结式口吻”，对方法边界交代不够克制。
4. 前置部分页码、正文页码与 Word 自动化脚本之间存在旧逻辑残留，需要再次核对是否真正按“摘要开始阿拉伯数字连续编码”生成。

## 二、指导老师视角的修改意见

1. 摘要不要把系统结论写成“总体来看已经很好”，而应明确“做了什么、结果说明什么、边界在哪里”。
2. 第3章应更像问题分析，而不是功能列表复述，需要说明图片资料检索和文档问答的典型任务链。
3. 第4章应把关键设计的理由说透，例如为什么文档解析要异步、为什么要做语义描述桥接、为什么要强调三存储一致性。
4. 第6章要补实验运行说明，尤其是离线脚本来源、结果文件来源、时延指标的使用边界，以及微调补充实验中可证实的运行线索。
5. 第6章对 `baseline_clip` 更强这一事实要保留，但同时解释为什么本文仍以语义描述桥接作为系统主方法。
6. 第7章要压缩空泛总结，明确区分“已完成工作”“结果能说明什么”“尚存不足与后续工作”。
7. 参考文献结构应更偏向核心论文、方法文献和必要的工程文档，不宜保留过多弱相关框架文档。

## 三、对应修改动作

1. 修改 [front_matter.md](E:\BiShe\Code2\MyProject\front_matter.md)
   - 将英文关键词改为 `Keywords:`
   - 重写中英文摘要结尾，明确主方法边界和工程贡献口径
2. 修改 [chapter_3_analysis.md](E:\BiShe\Code2\MyProject\chapter_3_analysis.md)
   - 增补图片资料检索和文档问答的典型使用链路
   - 强化“需求由任务链推导而来”的表达
3. 修改 [chapter_4_design.md](E:\BiShe\Code2\MyProject\chapter_4_design.md)
   - 具体说明异步文档解析、语义描述桥接、三存储一致性、多执行模式分流的设计原因
   - 删除“有两个好处”“更合理”等泛化表述
4. 修改 [chapter_5_implementation.md](E:\BiShe\Code2\MyProject\chapter_5_implementation.md)
   - 删除对 Vue 3、Vite、Element Plus、UnoCSS 四条弱相关文献的合并引用
5. 修改 [chapter_6_experiments.md](E:\BiShe\Code2\MyProject\chapter_6_experiments.md)
   - 新增“实验运行说明”
   - 增补时延指标适用边界说明
   - 增补微调补充实验中可证实的软件环境事实
   - 强化“为何仍采用语义描述桥接作为主方法”的讨论
6. 修改 [chapter_7_conclusion.md](E:\BiShe\Code2\MyProject\chapter_7_conclusion.md)
   - 收紧总结语气
   - 将后续展望收敛为三个更具体方向
7. 修改 [references.md](E:\BiShe\Code2\MyProject\references.md)
   - 删除 4 条前端框架官方文档引用
   - 将文献总数收敛为 40 条
8. 修改 [scripts/build_thesis_docx.py](E:\BiShe\Code2\MyProject\scripts\build_thesis_docx.py)
   - 将英文关键词标签生成逻辑改为 `Keywords:`
   - 保持前置部分摘要开始阿拉伯数字编码
   - 将正式构建改为“先生成临时文件，再覆盖最终成品”，解决最终输出路径上的 Word 自动化阻塞
9. 修改 [scripts/check_final_docx.py](E:\BiShe\Code2\MyProject\scripts\check_final_docx.py)
   - 新增 `Keywords:`、旧标签排除、参考文献 40 条、全文引文覆盖等检查项
   - 将检查改为“先复制检查副本，再打开检查”，解决直接打开最终文件时的 Word 阻塞

## 四、修改后的结果

1. 最终论文文件为 [张琪-本科毕业论文-定稿.docx](E:\BiShe\Code2\MyProject\docs\张琪-本科毕业论文-定稿.docx)。
2. 英文关键词标签已统一为 `Keywords:`，旧的 `Key Words` 已移除。
3. 参考文献数量为 40 条，正文已覆盖全部参考文献，且无旧编号残留。
4. 第3章、第4章、第6章和第7章的叙述更贴近毕业论文写法，减少了功能说明书式和模板化收束语气。
5. 语义描述桥接方法的定位已调整为“系统主链路中的核心桥接方案”，不再写成检索指标全面领先。
6. Word 自动化构建与检查流程都已修复，避免再次因为最终输出路径阻塞而卡住。

## 五、仍需人工终看的事项

1. 建议在 Word 中再人工目视一次 [张琪-本科毕业论文-定稿.docx](E:\BiShe\Code2\MyProject\docs\张琪-本科毕业论文-定稿.docx) 的封面换行、目录分页和个别段落分页效果。
2. 当前自动检查已确认摘要、Abstract、目录、正文、参考文献、致谢等结构存在，且关键词标签、参考文献数量和引文覆盖满足要求；如果导师对封面视觉布局有额外习惯要求，仍应以最终目视版本为准。
