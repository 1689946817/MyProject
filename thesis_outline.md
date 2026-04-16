# 本科毕业论文执行大纲

论文题目：**基于语义描述桥接的多模态RAG系统设计与实现**

总写作原则：
- 以代码、实验脚本和实验结果为第一手证据。
- 以学校模板和书写规范为版式约束。
- 以开题、中期、技术调研、系统分析、系统设计文档作为辅助材料，不直接拼接原文。

## 全文主线

论文主线采用“语义描述桥接 + 混合检索 + 会话化问答”的系统叙述方式。

- 系统核心场景：图片知识库的检索与问答。
- 系统扩展场景：PDF 文档知识库解析与问答。
- 实验重点场景：UniDoc-Bench 跨域文档图像检索与生成评测。
- 补充验证场景：已有微调实验结果作为扩展验证，不抢占系统主实验地位。

## 第1章 绪论

写作目标：
- 说明多模态知识管理与问答场景下的问题背景。
- 引出“直接用图像向量检索”和“只依赖 OCR 文本检索”的局限。
- 说明本项目为何采用语义描述桥接思路。
- 概述本文主要工作和章节安排。

主要证据来源：
- `README.md`
- `docs/开题报告_0112.docx`
- `docs/张琪-中期报告-v2.docx`
- `backend/app/main.py`
- `frontend/src/router/index.ts`

建议图表：
- 图1-1 论文研究内容与系统范围示意图

需要避免重复：
- 不在本章提前展开具体实现细节。
- 不把技术背景写成通用综述。

## 第2章 关键技术介绍

写作目标：
- 只介绍与本项目直接相关的技术基础。
- 为后续系统设计和实现提供必要铺垫。

建议小节：
1. 多模态大模型与图像语义描述
2. 向量检索与文本检索
3. 混合检索与重排
4. RAG 与多模态问答
5. PDF 文档解析与分块处理

主要证据来源：
- `docs/开发技术调研报告.docx`
- `backend/app/retrieval/retrievers.py`
- `backend/app/application/doc_parser.py`
- `evaluation/methods/unidoc_proposed.py`
- `evaluation/methods/unidoc_clip.py`
- `evaluation/methods/unidoc_ocr.py`

建议图表：
- 图2-1 语义描述桥接方法原理图
- 表2-1 本项目采用的关键技术与用途对应表

需要避免重复：
- 不重复第4章的系统架构图。
- 不写与项目无关的大模型发展史。

## 第3章 系统分析

写作目标：
- 从真实功能出发整理系统需求。
- 明确用户场景、业务流程、功能模块和非功能需求。

建议小节：
1. 应用场景分析
2. 功能需求分析
3. 非功能需求分析
4. 可行性分析

主要证据来源：
- `docs/系统分析报告.docx`
- `backend/app/api/routers/*.py`
- `frontend/src/views/*.vue`
- `backend/app/data/*.py`

建议图表：
- 图3-1 系统业务流程图
- 表3-1 功能需求列表
- 表3-2 非功能需求列表

需要避免重复：
- 不在本章详细解释数据库表字段实现。
- 不把需求分析写成设计章节。

## 第4章 系统设计

写作目标：
- 解释系统总体结构、模块划分、关键流程和数据组织方式。
- 说明为什么采用当前设计，而不是罗列全部源码细节。

建议小节：
1. 总体架构设计
2. 核心模块设计
3. 数据存储设计
4. 检索与问答流程设计
5. 文档解析流程设计

主要证据来源：
- `docs/系统设计报告.docx`
- `backend/app/langchain_integration/adapters.py`
- `backend/app/retrieval/retrievers.py`
- `backend/app/application/knowledge_management.py`
- `backend/app/application/doc_parser.py`
- `backend/app/data/models.py`
- `backend/app/data/doc_models.py`
- `backend/app/data/chat_models.py`

建议图表：
- 图4-1 系统总体架构图
- 图4-2 图片知识库处理流程图
- 图4-3 文档知识库处理流程图
- 图4-4 会话问答流程图
- 表4-1 核心模块职责表

需要避免重复：
- 不与第5章重复解释前端页面交互细节。
- 不把实验流程写进设计章节。

## 第5章 系统实现

写作目标：
- 结合真实代码说明系统“做了什么、怎么做的、为什么这样做”。
- 体现工程实现细节，但不过度贴源码。

建议小节：
1. 后端服务实现
2. 图片知识库实现
3. 文档知识库实现
4. 检索功能实现
5. 会话化问答实现
6. 前端交互实现
7. 配置与管理功能实现

主要证据来源：
- `backend/app/main.py`
- `backend/app/api/routers/kb.py`
- `backend/app/api/routers/docs.py`
- `backend/app/api/routers/search.py`
- `backend/app/api/routers/chat.py`
- `backend/app/api/routers/admin.py`
- `backend/app/application/*`
- `backend/app/retrieval/*`
- `frontend/src/views/KnowledgeBase.vue`
- `frontend/src/views/DocumentKB.vue`
- `frontend/src/views/Search.vue`
- `frontend/src/views/Chat.vue`

建议图表：
- 图5-1 图片上传与索引构建时序图
- 图5-2 文档解析与入库流程图
- 图5-3 检索页面交互示意图
- 图5-4 聊天页面来源回溯示意图

需要避免重复：
- 不重复第4章的抽象设计描述。
- 不将前端页面逐个控件流水账化。

## 第6章 实验设计与结果分析

写作目标：
- 基于真实脚本和真实结果还原实验流程。
- 如实分析优劣，不夸大结果。

建议小节：
1. 实验目标与实验环境
2. 数据集与评价指标
3. 检索实验设计与结果分析
4. 生成实验设计与结果分析
5. 微调补充实验分析
6. 局限性讨论

主要证据来源：
- `evaluation/metrics.py`
- `evaluation/run_unidoc_full_eval.py`
- `evaluation/run_unidoc_gen.py`
- `evaluation/run_unidoc_score.py`
- `evaluation/methods/*.py`
- `实验数据/检索器/analysis_2/tables/retrieval_summary_v2.csv`
- `实验数据/检索器/analysis_report_2.md`
- `实验数据/生成器/analysis_2/tables/generation_summary_v2.csv`
- `实验数据/生成器/analysis_report_2.md`
- `实验数据/微调/analysis_report_2.md`
- `实验数据/微调/analysis_2/tables/finetune_scores_wide_v2.csv`

建议图表：
- 表6-1 实验环境配置表
- 表6-2 检索实验指标定义表
- 表6-3 COCO 检索结果对比表
- 表6-4 UniDoc 跨域检索结果对比表
- 表6-5 生成实验结果对比表
- 表6-6 微调实验平均得分对比表
- 图6-1 检索实验主要指标柱状图
- 图6-2 微调训练曲线或阶段得分趋势图

需要避免重复：
- 不重复第5章的模块实现细节。
- 不把不同实验的指标混在同一个分析段落里。

## 第7章 总结与展望

写作目标：
- 回顾项目完成情况。
- 概括系统实现与实验验证得到的结论。
- 说明当前局限和可继续改进的方向。

建议小节：
1. 工作总结
2. 存在的问题
3. 后续展望

主要证据来源：
- 全文综合
- `实验数据/*`
- `docs/张琪-中期报告-v2.docx`

建议图表：
- 本章一般不强制插图，可仅保留文字总结

需要避免重复：
- 不重复摘要。
- 不写脱离工程现实的空泛展望。

## 参考文献、致谢、附录

参考文献：
- 来自开题和技术调研中已有文献条目
- 补充与最终实现直接相关的多模态检索、RAG、OCR、文档解析相关文献

致谢：
- 保持本科论文语气，简短真实

附录：
- 视篇幅决定是否附核心接口说明、实验补充表或部分参数配置说明

## 章节来源边界

| 章节 | 允许作为主证据的来源 | 辅助来源 | 禁止做法 |
| --- | --- | --- | --- |
| 第1章 | README、代码结构、开题/中期 | 技术调研 | 直接复述开题原文 |
| 第2章 | 代码、实验方法脚本 | 技术调研 | 写成百科综述 |
| 第3章 | 路由、前端页面、数据模型 | 系统分析报告 | 把设计内容混入需求 |
| 第4章 | 适配器、检索、解析、模型 | 系统设计报告 | 抽象图与实际代码脱节 |
| 第5章 | 后端、前端、配置、数据模型 | README | 源码逐行翻译 |
| 第6章 | `evaluation` 与 `实验数据` | 分析报告 | 杜撰实验数值和基线 |
| 第7章 | 全文事实 | 中期报告 | 夸大创新或写空泛口号 |

## 当前写作顺序

1. 完成四个基础中间文件。
2. 依次撰写七章 Markdown 草稿。
3. 合并后生成统一版内容。
4. 进行事实审校和语言审校。
5. 填充模板并输出最终 `docx`。
