# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于多模态大模型与双路检索的多模态 RAG 知识库系统。核心思路：用 MLLM 将图像"翻译"为结构化文本描述，把多模态检索转化为纯文本向量检索，支持文本→图像、图像→图像双路检索及 RAG 问答。

## 开发命令

### 后端
```bash
# 激活虚拟环境（Windows）
.venv\Scripts\activate

# 启动后端（端口 9090）
cd backend && python main.py

# 运行测试
cd backend && python -m pytest tests/ -v

# 运行单个测试文件
cd backend && python -m pytest tests/test_langchain_integration.py -v
```

### 前端
```bash
cd frontend && npm install && npm run dev   # 开发服务器（端口 5173）
cd frontend && npm run build               # 生产构建
```

### 离线评估
```bash
# 从项目根目录运行
python -m evaluation.run_offline_eval \
  --dataset-path data/coco_subset_eval.json \
  --method proposed \
  --top-k 10
# method 可选：proposed | baseline_text | baseline_clip
```

## 环境配置

复制 `backend/.env.example` 到 `backend/.env`，配置以下变量：
- `MLLM_BASE_URL / MLLM_API_KEY / MLLM_MODEL_NAME`：多模态模型（如 Qwen-VL）
- `EMBEDDING_BASE_URL / EMBEDDING_API_KEY / EMBEDDING_MODEL_NAME`：Embedding 模型（如 BGE-m3）
- `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL_NAME`：文本生成模型

所有模型接口均使用 OpenAI API 格式（阿里百炼等兼容服务）。

## 架构概览

### 重构状态：LangChain 集成

后端已从原始实现重构为 LangChain 架构。**原始实现已移至 `backend/app/legacy/`，不再被主流程使用。**

当前活跃代码路径：
```
backend/app/
├── main.py                    # FastAPI 应用入口
├── core/config.py             # pydantic-settings 配置（从 .env 加载）
├── data/
│   ├── models.py              # ImageRecord ORM 模型（UUID 主键）
│   ├── database.py            # SQLAlchemy + SQLite 连接
│   └── storage.py             # 图片文件存储（backend/storage/）
├── langchain_integration/     # 当前核心业务逻辑
│   ├── models.py              # MultimodalChatModel（封装 MLLM）
│   ├── vectorstores.py        # ChromaVectorStore（封装 ChromaDB）
│   ├── retrievers.py          # MultimodalRetriever（双路检索）
│   ├── chains.py              # ImageDescriptionChain、RAGChain（LCEL）
│   └── adapters.py            # LangChainAdapter（供 API 路由调用的门面）
├── api/routers/
│   ├── kb.py                  # POST /api/knowledge-base/upload
│   ├── search.py              # POST /api/search/text-to-image, image-to-image
│   └── chat.py                # POST /api/rag/chat
├── application/schemas.py     # Pydantic 响应模型
└── legacy/                    # 旧实现（已废弃，仅供参考）
    ├── semantic/
    ├── retrieval/
    └── application/
```

### 关键设计决策

**LangChain 适配器模式**：`LangChainAdapter`（`adapters.py`）是 API 路由与 LangChain 组件之间的唯一接口。路由层不直接调用 Chain 或 Retriever，只调用 adapter 的方法。

**双路检索**：`MultimodalRetriever` 统一处理两种查询：
- 文本查询：直接 Embedding → ChromaDB 向量检索
- 图像查询：先调 MLLM 生成描述 → 再走文本检索路径

**RAG 流程**：`RAGChain` 检索到图像后，读取原始图片文件转为 base64，连同用户问题一起构建多模态 Prompt 传给 MLLM 生成回答。

**单例模式**：`get_langchain_adapter()`、`get_image_description_chain()`、`get_rag_chain()` 均使用模块级全局变量缓存实例，避免重复初始化模型连接。

### 数据存储

| 存储 | 位置 | 内容 |
|------|------|------|
| SQLite | `backend/app.db` | `image_records` 表，存图像元数据和描述 |
| ChromaDB | `backend/chroma_data/` | 主系统图片集合 `images_main_kb`，COCO proposed 评测集合 `images_coco_proposed`，文档集合 `documents_text` |
| 图片文件 | `backend/storage/` | 以 UUID 命名的原始图片 |

三处存储的 ID 必须保持一致（均为 UUID 字符串）。

### 前端架构

Vue 3 + TypeScript + Vite，三个主视图：
- `KnowledgeBase.vue`：图片上传与描述查看
- `Search.vue`：文本/图像检索
- `Chat.vue`：RAG 聊天

API 调用通过 `src/api/` 下的模块封装，Axios 实例配置在 `src/api/http.ts`。

## 注意事项

- `backend/app/semantic/prompts.py` 仍被 `langchain_integration/chains.py` 引用（`IMAGE_DESCRIPTION_PROMPT`），不在 legacy 目录中
- CORS 使用正则匹配 `localhost` 和 `127.0.0.1` 的 5173-5175 端口
- `ImageRecord.status` 取值：`Processing` | `Completed` | `Failed`
- 评估模块在 `evaluation/` 目录，独立于后端服务运行
