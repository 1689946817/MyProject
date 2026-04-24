## 项目简介

本项目实现了一个 **基于多模态大模型与双路检索的多模态 RAG 知识库系统**，支持：

- 文本→图像检索、图像→图像检索
- 基于检索结果的多模态 RAG 问答
- PDF 文档知识库、异步解析与进度查询
- 文档解析任务队列、批量导入、健康检查与基础指标暴露
- 图片/文档去重与版本管理、回答反馈闭环
- 在 MS-COCO 子集上的离线检索评测与多方法对比实验（Proposed / Baseline）

后端基于 `FastAPI + SQLite + ChromaDB`，前端基于 `Vue3 + TS + Vite + Element Plus`。

---

## 目录结构概览

- `backend/`：FastAPI 后端
  - `app/core/config.py`：环境变量与全局配置
  - `app/data/`：数据库模型与图片存储
  - `app/semantic/`：多模态模型封装与图像描述生成
  - `app/retrieval/`：Embedding 客户端与 Chroma 向量检索
  - `app/application/`：双路检索调度与 RAG 引擎
  - `app/api/routers/`：REST API 路由
  - `main.py`：后端启动入口
- `frontend/`：前端工程（Vue3 + Element Plus）
  - `src/views/KnowledgeBase.vue`：知识库管理（图片上传与描述查看）
  - `src/views/Search.vue`：文本/图像检索界面
  - `src/views/Chat.vue`：RAG 聊天界面
- `evaluation/`：离线对比实验与评测
  - `metrics.py`：Recall@K、mAP、MRR 等检索指标
  - `datasets/coco_subset.py`：MS-COCO 子集 JSON 加载
  - `methods/`：不同方法的检索实现（Baseline / Proposed）
  - `run_offline_eval.py`：命令行离线评测脚本

---

## 环境准备与安装

### 1. 创建 Python 虚拟环境并安装后端依赖

在项目根目录下：

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置 `.env`

在 `backend/` 目录下复制示例配置：

```bash
cd backend
cp .env.example .env
```

然后根据你在阿里百炼（或其它云平台）上开通的：

- 多模态模型（如 Qwen-VL）
- Embedding 模型（如 BGE-m3）
- 文本 LLM 模型

填写对应的 `*_BASE_URL`、`*_API_KEY` 与 `*_MODEL_NAME`。

---

## 运行后端与前端

### 1. 启动 FastAPI 后端

在 `backend/` 下：

```bash
E:/Pyenvironment/multimodal-rag/python.exe main.py
```

默认监听 `http://localhost:9090`，可以通过：

```bash
curl http://localhost:9090/api/health
```

检查健康状态。

### 2. 启动文档解析 worker

文档上传和重处理不再依赖进程内 `BackgroundTasks`，而是通过数据库任务队列驱动。需要额外启动一个 worker：

```bash
cd backend
E:/Pyenvironment/multimodal-rag/python.exe -m app.workers.task_worker
```

如果 worker 未启动，文档会进入 `queued` 状态，但不会继续解析。

### 3. 启动前端

在项目根目录：

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:5173` 即可看到前端界面：

- 左侧导航在三个页面间切换：
  - “知识库管理”：上传图片，自动生成结构化描述并入库
  - “文档知识库”：上传 PDF，查看解析进度、文本片段和派生图片
  - “图像检索”：文本→图像、图像→图像检索结果列表
  - “RAG 智能问答”：输入问题（可带图像），查看回答与引用图像

---

## 后端运行与验收要点

### 1. 建议启动顺序

```bash
cd backend
E:/Pyenvironment/multimodal-rag/python.exe main.py
E:/Pyenvironment/multimodal-rag/python.exe -m app.workers.task_worker
cd ../frontend
npm run dev
```

### 2. 核心接口检查

- 健康检查：`GET /api/health`
- 存活检查：`GET /api/health/live`
- 就绪检查：`GET /api/health/ready`
- 依赖状态：`GET /api/health/deps`
- 指标：`GET /api/metrics`
- 任务列表：`GET /api/jobs`
- 批量导入：`POST /api/imports/batch`

### 3. 文档知识库相关接口

- 上传文档：`POST /api/docs/upload`
- 查看解析进度：`GET /api/docs/{doc_id}/progress`
- 查看解析结果：`GET /api/docs/{doc_id}/result`
- 重处理文档：`POST /api/docs/{doc_id}/reprocess`
- 查看版本历史：`GET /api/docs/{doc_id}/versions`
- 上传新版本：`POST /api/docs/{doc_id}/versions`

### 4. 图片知识库相关接口

- 上传图片：`POST /api/knowledge-base/upload`
- 重处理图片：`POST /api/knowledge-base/{image_id}/reprocess`
- 查看版本历史：`GET /api/knowledge-base/{image_id}/versions`
- 上传新版本：`POST /api/knowledge-base/{image_id}/versions`

### 5. 问答反馈接口

- 提交反馈：`POST /api/chat/messages/{message_id}/feedback`

---

## 演示建议流程

建议按下面顺序演示，稳定且容易说明系统亮点：

1. 打开 `/api/health/ready` 和 `/api/metrics`，说明系统具备基础可观测性。
2. 上传一份 PDF，展示文档进入队列、worker 消费、进度更新和解析结果。
3. 上传一张图片，展示自动描述生成、去重逻辑和版本接口。
4. 在检索页展示文本搜图或图搜图。
5. 在聊天页提问，展示来源回溯、引用和反馈接口。

---

## 当前后端已落地的工程增强点

- 文档解析由任务队列驱动，支持任务查询、重试和 worker 心跳。
- 新增健康检查与 Prometheus 风格文本指标接口。
- 图片与文档支持内容去重、逻辑资源归组和版本历史。
- 回答支持反馈闭环，便于收集错误样本。
- 文档检索链已补充 query rewrite、BM25、RRF、rerank 和相关性过滤。

---

## 运行离线对比实验（MS-COCO 子集）

### 1. 准备 COCO 子集与预处理 JSON

你需要从 MS-COCO 中选取一个子集，并准备一个 JSON 文件（例如 `data/coco_subset_eval.json`），
每个元素形如：

```json
{
  "query": "a child playing football on the grass",
  "relevant_ids": ["000000123456", "000000234567"]
}
```

其中 `relevant_ids` 应与系统中 `ImageRecord.id`（以及向量库中的 doc_id）一致。对于离线 COCO proposed 实验，对应向量应写入 `images_coco_proposed`；主系统在线数据默认写入 `images_main_kb`。

### 2. 构建向量索引

- **Proposed 方法：MLLM 结构化描述 + 文本检索**
  1. 启动后端。
  2. 通过前端或脚本批量上传 COCO 子集图片到 `/api/knowledge-base/upload`；
  3. 主系统在线图片知识库会将描述与图像写入数据库和 Chroma 集合 `images_main_kb`；若用于 COCO proposed 离线评测，请将评测索引单独构建到 `images_coco_proposed`，避免与主系统在线数据混用。

- **Baseline A：仅文本检索（纯文本 RAG）**
  - 建议你将 COCO 原始 caption 或其它文本描述单独构建为一个 Chroma 集合 `images_text_only`，
    其 `id` 与 ground truth 中的 `relevant_ids` 对齐。完成后即可使用本仓库中的基线代码进行评测。

- **Baseline B：跨模态检索（qwen3-vl-embedding）**
  - 使用 qwen3-vl-embedding 多模态融合向量模型，支持文本→图像和图像→图像检索。
  - 首先构建向量索引：`python -m evaluation.build_clip_index`
  - 该基线使用独立的 Chroma 集合 `images_multimodal_embedding`。

### 3. 运行检索评测脚本

在项目根目录下，使用 Python 模块方式运行：

```bash
python -m evaluation.run_offline_eval \
  --dataset-path data/coco_subset_eval.json \
  --method proposed \
  --top-k 10
```

- `--method proposed`：评测本项目提出的方法（MLLM 描述 + 文本检索）；
- `--method baseline_text`：评测纯文本检索基线（前提是已构建好 `images_text_only` 集合）；
- `--method baseline_clip`：评测跨模态检索基线（前提是已构建好 `images_multimodal_embedding` 集合）。

脚本会输出：

- `Recall@1, Recall@5, Recall@K`
- `MRR`
- `mAP@K`

可将结果记录到论文/开题报告的实验章节中。

> 提示：Baseline B 已实现，使用 qwen3-vl-embedding 多模态融合向量模型进行跨模态检索。

---

## 你需要做的主要操作总结

1. **配置云端模型**：在 `.env` 中填好多模态模型、Embedding 模型与 LLM 的接口信息。
2. **启动后端与 worker**：`E:/Pyenvironment/multimodal-rag/python.exe backend/main.py` 与 `E:/Pyenvironment/multimodal-rag/python.exe -m app.workers.task_worker`。
3. **启动前端**：`npm run dev`。
4. **构建知识库**：在前端“知识库管理”和“文档知识库”页面上传图片/PDF。
5. **互动体验**：在“图像检索”和“RAG 智能问答”页面体验检索、问答、反馈和来源回溯功能。
6. **准备 COCO 子集 JSON 与向量库**：保证 `relevant_ids` 与系统内部 ID 对齐。
7. **运行离线评测脚本**：使用 `evaluation/run_offline_eval.py` 分别对 Proposed 与 Baseline 方法评测，
   收集 Recall、mAP、MRR 等指标用于论文撰写与对比实验分析。
