# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个基于多模态大模型与双路检索的多模态 RAG 知识库系统，支持：
- 文本→图像检索、图像→图像检索
- 基于检索结果的多模态 RAG 问答
- 在 MS-COCO 子集上的离线检索评测与多方法对比实验

## 开发环境与依赖

### 后端 (Python)
- 虚拟环境：`.venv/`（已存在）
- 依赖：`backend/requirements.txt`
- 启动命令：`cd backend && python main.py`
- 端口：9094（后端），8000（README 中提到的备用端口）
- 健康检查：`GET /api/health`

### 前端 (Vue3 + TypeScript)
- 依赖：`frontend/package.json`
- 启动命令：`cd frontend && npm install && npm run dev`
- 端口：5173
- 构建：`npm run build`

### 环境配置
1. 复制 `backend/.env.example` 到 `backend/.env`
2. 配置以下云端模型服务（阿里百炼等）：
   - `MLLM_*`：多模态模型（如 Qwen-VL）
   - `EMBEDDING_*`：文本 Embedding 模型（如 BGE-m3）
   - `LLM_*`：文本生成模型

## 架构概览

### 后端架构 (`backend/app/`)
- **`main.py`**：FastAPI 应用入口，配置 CORS 和路由
- **`core/config.py`**：环境变量配置，使用 `pydantic-settings`
- **`data/`**：数据层
  - `database.py`：SQLAlchemy 数据库连接
  - `models.py`：`ImageRecord` 模型（主键为 UUID）
  - `storage.py`：图片文件存储
- **`semantic/`**：多模态模型层
  - `mllm_client.py`：多模态模型客户端
  - `description_service.py`：图像描述生成服务
  - `prompts.py`：提示词模板
- **`retrieval/`**：检索层
  - `embedding_client.py`：Embedding 客户端
  - `vector_store.py`：ChromaDB 向量存储
  - `rerank.py`：重排序（预留）
- **`application/`**：业务逻辑层
  - `dispatcher.py`：双路检索调度（文本/图像检索）
  - `rag_engine.py`：RAG 问答引擎
  - `llm_client.py`：文本 LLM 客户端
- **`api/routers/`**：API 路由
  - `kb.py`：知识库管理（图片上传）
  - `search.py`：检索接口
  - `chat.py`：RAG 问答接口

### 前端架构 (`frontend/`)
- **`src/views/`**：页面组件
  - `KnowledgeBase.vue`：知识库管理（图片上传与描述查看）
  - `Search.vue`：文本/图像检索界面
  - `Chat.vue`：RAG 聊天界面
- **`src/api/`**：API 客户端
  - `http.ts`：Axios 实例配置
  - `kb.ts`、`search.ts`、`chat.ts`：各模块 API 调用

### 评估模块 (`evaluation/`)
- **`run_offline_eval.py`**：离线评测主脚本
- **`datasets/coco_subset.py`**：MS-COCO 子集数据加载
- **`methods/`**：不同检索方法实现
  - `proposed_multimodal_rag.py`：本项目提出的方法
  - `baseline_text_rag.py`：纯文本检索基线
  - `baseline_clip_retrieval.py`：跨模态检索基线（使用 qwen3-vl-embedding）
- **`metrics.py`**：检索指标（Recall@K、mAP、MRR）
- **`evaluation_module.py`**：评估模块主逻辑

## 关键工作流程

### 1. 图片上传与知识库构建
1. 前端调用 `POST /api/knowledge-base/upload`
2. 后端保存图片文件到 `backend/storage/`
3. 调用多模态模型生成结构化描述
4. 将描述存入 SQLite 数据库和 ChromaDB 向量库
5. Chroma 集合名称：`images_semantic_desc`

### 2. 双路检索流程
- **文本检索**：查询文本 → Embedding → Chroma 向量检索
- **图像检索**：上传图片 → 多模态模型生成描述 → 文本检索
- 检索结果包含：图像 ID、文件路径、描述文本

### 3. RAG 问答流程
1. 用户输入问题（可选上传图片）
2. 执行双路检索获取相关图像
3. 将检索到的原始图像转换为base64编码
4. 将图像和问题一起传给多模态大模型生成答案
5. 返回答案和引用的图像列表

### 4. 离线评估流程
1. 准备 MS-COCO 子集 JSON 文件
2. 确保图像 ID 与系统 `ImageRecord.id` 对齐
3. 运行 `python -m evaluation.run_offline_eval`
4. 输出 Recall@K、MRR、mAP 等指标

## 数据库与存储

### SQLite 数据库
- 文件：`backend/app.db`（开发环境）
- 表：`image_records`（存储图像元数据和描述）
- 主键：UUID 字符串，与 ChromaDB 文档 ID 对齐

### ChromaDB 向量库
- 持久化路径：`backend/chroma_data/`
- 集合：`images_semantic_desc`
- 文档：图像的结构化描述文本
- 元数据：包含 `file_path`、`id` 等

### 图片文件存储
- 路径：`backend/storage/`
- 命名：使用 UUID 作为文件名

## 开发注意事项

1. **API 端点前缀**：所有 API 路由都有 `/api/` 前缀
2. **CORS 配置**：已配置允许 `localhost:5173` 和 `127.0.0.1:5173`
3. **错误处理**：注意处理模型 API 调用失败的情况
4. **异步操作**：图片处理和模型调用使用异步函数
5. **ID 对齐**：确保 SQLite、ChromaDB、文件系统中的 ID 一致

## 测试与评估

### 运行离线评估
```bash
python -m evaluation.run_offline_eval \
  --dataset-path data/coco_subset_eval.json \
  --method proposed \
  --top-k 10
```

### 评估方法
- `proposed`：本项目方法（MLLM 描述 + 文本检索）
- `baseline_text`：纯文本检索基线
- `baseline_clip`：跨模态检索基线（使用 qwen3-vl-embedding 多模态融合向量）

### 评估指标
- Recall@1, Recall@5, Recall@K
- Mean Reciprocal Rank (MRR)
- Mean Average Precision (mAP@K)

## 故障排除

1. **后端启动失败**：检查 `.env` 配置和模型 API 密钥
2. **图片上传失败**：检查 `backend/storage/` 目录权限
3. **检索无结果**：确认 ChromaDB 集合已正确构建
4. **前端无法连接后端**：检查 CORS 配置和后端端口
5. **评估脚本错误**：确保 COCO 子集 JSON 格式正确且 ID 对齐