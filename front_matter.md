# 中文摘要

随着图片资料、扫描文档和多模态信息不断积累，传统以纯文本为中心的知识库系统在资料组织、检索和问答方面逐渐暴露出局限。针对图像内容难以直接进入文本检索链路、文档页面中视觉信息和版面信息不易被有效利用等问题，本文结合实际项目实现，设计并实现了一套基于语义描述桥接的多模态 RAG 系统。

系统采用前后端分离架构，后端基于 FastAPI 实现图片知识库、文档知识库、检索、会话问答和系统管理等功能，前端基于 Vue 3 实现图片管理、文档解析进度展示、文本搜图、图搜图和多轮问答交互。在知识入库阶段，系统利用多模态大模型为图片生成语义描述，并将该描述作为桥接表示接入向量索引和文本检索流程；对于 PDF 文档，系统进一步实现了文本抽取、句子感知分块、页面图像和表格裁剪提取等处理流程。在检索与问答阶段，系统结合查询改写、向量检索、BM25 检索、倒数排序融合和重排，构建了可回溯的多模态 RAG 链路。

在实验部分，本文依据项目中的真实评测脚本和结果文件，对语义描述桥接方法、多模态向量基线和 OCR 文本基线进行了比较。结果表明，在 UniDoc 跨域检索实验中，语义描述桥接方法的 Recall@10 为 0.9611，MRR 为 0.9158，与多模态向量基线保持接近；在 UniDoc subset100 生成实验中，语义描述桥接方法的答案正确性为 0.86，图像上下文相关性为 0.9286，而无检索生成基线的答案正确性仅为 0.24。上述结果说明，语义描述桥接虽然并非当前检索指标上的最强方案，但能够在统一检索与问答链路中保持稳定表现，适合作为当前系统的核心桥接方式。本文工作的重点在于完成面向真实资料场景的系统实现，并基于可回溯实验材料给出较为稳妥的验证。

**关键词：** 多模态 RAG；语义描述桥接；混合检索；文档知识库；会话化问答

# Abstract

With the rapid accumulation of image materials, scanned documents, and other multimodal resources, conventional text-centered knowledge base systems show clear limitations in organization, retrieval, and question answering. To address the difficulty of integrating image content into text-based retrieval pipelines and the weak utilization of visual and layout information in document pages, this thesis designs and implements a multimodal RAG system based on semantic description bridging.

The system adopts a front-end and back-end separated architecture. The back end is built on FastAPI and provides image knowledge base management, document knowledge base management, retrieval, conversational question answering, and system administration. The front end is implemented with Vue 3 and supports image management, document parsing progress display, text-to-image search, image-to-image search, and multi-turn interaction. During knowledge ingestion, the system uses a multimodal large model to generate semantic descriptions for images, and treats these descriptions as bridge representations for vector indexing and text retrieval. For PDF documents, the system further supports text extraction, sentence-aware chunking, and visual content extraction such as page images and table crops. During retrieval and answering, the system combines query rewriting, vector retrieval, BM25 retrieval, reciprocal rank fusion, and reranking to form a traceable multimodal RAG pipeline.

The experiments in this thesis are based on real evaluation scripts and result files in the project. The proposed semantic description bridging method is compared with a multimodal embedding baseline and an OCR-based text baseline. In the UniDoc cross-domain retrieval experiment, the proposed method reaches a Recall@10 of 0.9611 and an MRR of 0.9158, remaining close to the multimodal embedding baseline. In the UniDoc subset100 generation experiment, the proposed method achieves an answer correctness score of 0.86 and an image-context relevancy of 0.9286, while direct generation without retrieval only reaches 0.24 in answer correctness. These results indicate that semantic description bridging is not the strongest retrieval option in every setting, yet it remains stable in a unified retrieval-and-answering pipeline and fits the current system as its main bridge representation. The contribution of this work lies in completing a practical system for real multimodal materials and validating it with traceable project evidence.

**Keywords:** multimodal RAG; semantic description bridging; hybrid retrieval; document knowledge base; conversational question answering

# 致谢

本课题从选题、实现到论文撰写，得到了指导教师在研究方向、系统设计和论文修改方面的持续指导。在项目开发和实验整理过程中，老师提出的意见帮助我及时收敛了实现范围，也使论文内容能够更贴近系统实际完成情况。在此表示诚挚感谢。

同时，感谢学院老师在毕业设计阶段提供的学习和管理支持，感谢同学在项目测试和交流过程中的帮助。最后，感谢家人在毕业设计期间给予的理解与支持。
