# 多模态 RAG 图文检索智能问答系统后端升级方案

> 生成日期：2026-03-31
> 适用项目：`E:\BiShe\Code2\MyProject`

---

## 1. 背景与现状判断

当前项目已经具备较完整的核心闭环能力：

- 图片知识库上传
- 图像描述生成
- 文本→图像检索
- 图像→图像检索
- 多模态 RAG 问答
- 文档知识库解析与接入
- 基础管理端接口

现阶段最值得补齐的，不再是“能不能检索、能不能问答”，而是以下四类主流系统能力：

1. **可用性**：历史对话、会话列表、消息记录
2. **可解释性**：引用来源、检索证据、可追溯回答
3. **可管理性**：筛选、历史、反馈、相似推荐
4. **可扩展性**：为前端升级、论文展示、后续评估提供稳定接口

---

## 2. 推荐功能清单 + 优先级分层

### P0：必须优先补齐

#### 2.1 会话管理 / 历史对话
建议加入：
- 创建会话
- 会话列表
- 获取某个会话的消息历史
- 会话重命名
- 删除会话
- 聊天接口自动挂接 `session_id`

为什么优先：
- 主流问答系统标配
- 你当前 `ChatResponse` 已经有 `session_id` 字段，适合继续完善
- 也是前端 `Chat.vue` 最自然的升级方向

建议接口：
- `POST /api/chat/sessions`
- `GET /api/chat/sessions`
- `GET /api/chat/sessions/{session_id}/messages`
- `PATCH /api/chat/sessions/{session_id}`
- `DELETE /api/chat/sessions/{session_id}`
- `POST /api/rag/chat`

#### 2.2 消息级存储与上下文追踪
建议加入：
- 用户消息、助手消息持久化
- 每条回答关联检索结果快照
- 记录当次检索参数（`top_k`、检索模式、过滤条件）
- 记录消息时间戳

为什么优先：
- 不仅是聊天记录，也是实验可复现、系统可分析的基础
- 后续反馈、导出、统计都依赖它

建议数据模型：
- `ChatSession`
- `ChatMessage`
- `MessageSource`

#### 2.3 引用溯源 / 检索证据返回
建议加入：
- 每条回答返回引用的图片 / 文档片段
- 明确返回来源类型：`image` / `document`
- 返回相关度分数、来源 ID、文件路径、摘要
- 最好区分“检索到了哪些”与“最终作为引用返回了哪些”

为什么优先：
- 主流 RAG 系统强调答案依据
- 对论文、答辩、系统可信度都很重要

#### 2.4 检索参数化接口
建议加入：
- `top_k`
- `candidate_k`
- 是否启用重排
- 检索模式（仅图片 / 仅文档 / 混合）
- 是否启用 query transform
- 相似度阈值
- 过滤条件

为什么优先：
- 这对实验系统、研究系统和前端调参都非常重要

#### 2.5 知识库元数据过滤
建议加入：
- 按数据集过滤
- 按上传时间过滤
- 按状态过滤
- 按来源类型过滤
- 预留标签过滤

为什么优先：
- 是主流检索系统标准能力
- 能显著提升“查得准”和“可管理性”

### P1：强烈建议加入

#### 2.6 搜索历史 / 最近查询
- 保存最近文本查询
- 保存图搜图历史
- 支持清空历史

#### 2.7 问答反馈机制
- 对回答点赞 / 点踩
- 可选填写反馈原因
- 关联 `session_id + message_id`

#### 2.8 相似图片推荐 / Related Results
- 查看某张图时推荐相似图片
- 支持“以结果为中心继续探索”
- 可复用图搜图链路

### P2：推荐作为增强项
- 多轮对话上下文压缩 / 摘要记忆
- Query Rewrite / Query Decomposition
- 混合检索策略切换
- 管理端统计分析
- 多知识库 / 多集合选择

### P3：后续扩展
- 用户体系 / 权限隔离
- 流式输出 SSE / WebSocket
- 异步任务中心
- 标签与分类
- 首页主动推荐

---

## 3. 推荐采用的一套方案

推荐方案：**会话化多模态 RAG 后端升级方案**

### 核心目标
把系统从“能上传、能检索、能单轮问答”升级成一个更完整的：

- 支持会话与历史的问答系统
- 支持引用与证据的 RAG 系统
- 支持筛选、历史、相似推荐的检索系统

### 推荐功能范围

#### 模块 A：会话与历史对话
- 创建新会话
- 获取会话列表
- 获取会话详情
- 获取某个会话下的消息历史
- 会话重命名
- 删除会话
- 聊天接口支持传入 `session_id`
- 不传 `session_id` 时自动创建新会话

#### 模块 B：消息持久化与引用溯源
- 保存用户消息
- 保存助手消息
- 保存该轮检索结果快照
- 返回回答引用来源
- 区分来源类型：图片 / 文档
- 返回来源 ID、标题/摘要、相似度分数、文件路径或资源标识

#### 模块 C：检索参数化
- `top_k`
- `candidate_k`
- 是否启用重排
- 检索范围：图片 / 文档 / 混合
- 是否启用 query transform
- 相似度阈值
- 可选过滤条件入口

#### 模块 D：元数据过滤
- 按资源类型过滤
- 按状态过滤
- 按时间范围过滤
- 按集合 / 知识库过滤
- 预留标签过滤字段

#### 模块 E：轻量增强功能
- 搜索历史
- 问答反馈（点赞/点踩）
- 相似图片推荐接口

### 本轮不建议优先做的内容
- 用户登录 / 权限体系
- 流式输出重构
- 复杂异步任务中心
- 长对话摘要记忆
- 多租户知识库隔离
- 高级 Agentic orchestration 对话编排

---

## 4. 详细实现计划（阶段划分）

### Phase 1：会话与消息能力
目标：
- 新增会话表和消息表
- 支持会话 CRUD
- 支持消息历史拉取
- `POST /api/rag/chat` 支持 `session_id`
- 不传 `session_id` 时自动创建会话

建议新增文件：
- `backend/app/data/chat_models.py`
- `backend/app/application/chat_service.py`

建议修改文件：
- `backend/app/data/database.py`
- `backend/app/application/schemas.py`
- `backend/app/api/routers/chat.py`
- `backend/app/main.py`
- `backend/app/langchain_integration/adapters.py`

建议表：

#### `chat_sessions`
- `id: str(UUID)`
- `title: str`
- `created_at: datetime`
- `updated_at: datetime`
- `last_message_at: datetime | None`

#### `chat_messages`
- `id: str(UUID)`
- `session_id: str(FK -> chat_sessions.id)`
- `role: str` (`user` / `assistant`)
- `content: Text`
- `message_type: str | None`
- `retrieval_params_json: JSON | None`
- `created_at: datetime`

### Phase 2：可追溯 RAG
目标：
- 每轮聊天持久化 user / assistant message
- 聊天响应返回 `sources`
- 每条 assistant message 关联检索快照
- 保留当次检索参数

建议表：

#### `message_sources`
- `id: str(UUID)`
- `message_id: str(FK -> chat_messages.id)`
- `source_type: str` (`image` / `document`)
- `source_id: str`
- `score: float | None`
- `title: str | None`
- `content_snapshot: Text | None`
- `file_path: str | None`
- `metadata_json: JSON | None`

### Phase 3：检索参数化与元数据过滤
目标：
- `/api/rag/chat` 和 `/api/search/*` 支持参数控制
- 支持 metadata filter
- 支持 retrieval scope
- 支持 rerank 开关、阈值控制

### Phase 4：轻量增强功能
- 搜索历史
- 问答反馈
- 相似图片接口

---

## 5. 基于当前代码的实际落点分析

### 当前关键文件

#### `backend/app/application/schemas.py`
现状：
- 已有 `SearchResultItem`
- 已有 `TextSearchRequest` / `TextSearchResponse`
- 已有 `ImageSearchResponse`
- 已有 `ChatResponse`
- `ChatResponse` 中已有 `session_id` 字段，但结构仍较简陋

结论：
- 这是本次接口升级的核心 schema 文件
- 需要补齐 session / message / citation / filter / feedback / history 相关模型

#### `backend/app/api/routers/chat.py`
现状：
- 当前用内存 `OrderedDict` 维护 `_chat_sessions`
- `POST /api/rag/chat` 通过 `Form` 接收 `query/top_k/session_id`
- 支持 SSE 流式接口
- 目前历史对话并未落库

结论：
- 需要把“内存会话”替换为“数据库会话”
- 保留现有路由前缀 `/api/rag`
- 增加 `/api/chat/sessions` 等 REST 接口

#### `backend/app/api/routers/search.py`
现状：
- 仅支持 `/text-to-image` 与 `/image-to-image`
- 目前请求参数只有 `query` / `top_k`
- 尚无 filters、history、similar-image 相关接口

结论：
- 这是检索增强的主要落点

#### `backend/app/langchain_integration/adapters.py`
现状：
- 已封装上传、检索、RAG 问答
- `rag_chat()` 支持 `chat_history`
- `text_to_image_search()` / `image_to_image_search()` 已是统一调用入口

结论：
- 适合作为会话化编排、引用来源生成、搜索历史记录的高层入口

#### `backend/app/langchain_integration/retrievers.py`
现状：
- 已支持 Multi-Query、混合检索、CrossEncoder 精排
- 当前 `top_k`、`candidate_k` 来自配置或默认值
- 还没有显式接收 per-request filters / retrieval_scope

结论：
- 很适合继续扩展“参数化检索”

#### `backend/app/langchain_integration/vectorstores.py`
现状：
- `similarity_search` / `similarity_search_with_score` 已支持 `filter`
- 但上层 `search_by_text()` 还没有暴露 filter 参数

结论：
- 支持 metadata filter 的底层能力已经有一部分，改造成本较低

#### `backend/app/data/models.py`
现状：
- 只有 `ImageRecord`
- 已有 `status`、`source_dataset`、`tags`、`extra_metadata`

结论：
- 适合保留图像模型，新增 `chat_models.py` 存放会话相关表

#### `backend/app/main.py`
现状：
- 使用 `Base.metadata.create_all(bind=engine)` 建表
- 显式导入 `models`、`doc_models`

结论：
- 若新增 `chat_models.py`，需要在这里导入，确保建表生效

---

## 6. 推荐的目录演进方式

```text
backend/app/
├── api/routers/
│   ├── chat.py
│   ├── search.py
│   └── ...
├── application/
│   ├── schemas.py
│   ├── chat_service.py
│   ├── search_service.py
│   └── ...
├── data/
│   ├── database.py
│   ├── models.py
│   ├── chat_models.py
│   └── ...
├── langchain_integration/
│   ├── adapters.py
│   ├── retrievers.py
│   ├── vectorstores.py
│   └── ...
```

职责划分：
- `routers/`：HTTP 请求/响应层
- `application/chat_service.py`：会话、消息、反馈、历史
- `application/search_service.py`：搜索历史、similar image
- `langchain_integration/adapters.py`：统一编排 RAG/检索调用
- `data/chat_models.py`：新增 ORM 模型

---

## 7. 逐文件修改清单

### 7.1 `backend/app/application/schemas.py`

**当前作用**
定义 API 请求/响应模型。

**需要新增**
- `RetrievalFilter`
- `RetrievalOptions`
- `ChatRequest`
- `CitationSource`
- `ChatSessionCreateRequest`
- `ChatSessionUpdateRequest`
- `ChatSessionOut`
- `ChatMessageOut`
- `MessageFeedbackRequest`
- `MessageFeedbackOut`
- `SearchHistoryOut`
- `SearchHistoryResponse`
- `DeleteResponse`

**需要调整**
- `TextSearchRequest`：支持 `candidate_k`、`enable_rerank`、`retrieval_scope`、`enable_query_transform`、`score_threshold`、`filters`
- `TextSearchResponse`：可选增加 `applied_filters`、`retrieval_params`
- `ImageSearchResponse`：同上
- `ChatResponse`：从 `answer + results + session_id` 升级为 `session_id + message_id + answer + sources + retrieval_params + created_at`

**建议新增核心模型结构**

```python
class RetrievalFilter(BaseModel):
    source_dataset: str | None = None
    status: str | None = None
    source_type: str | None = None
    tags: list[str] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
```

```python
class RetrievalOptions(BaseModel):
    top_k: int = 5
    candidate_k: int | None = None
    enable_rerank: bool = True
    retrieval_scope: str = "mixed"
    enable_query_transform: bool = False
    score_threshold: float | None = None
    filters: RetrievalFilter | None = None
```

```python
class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    retrieval: RetrievalOptions = RetrievalOptions()
```

```python
class CitationSource(BaseModel):
    source_type: str
    source_id: str
    title: str | None = None
    description: str | None = None
    file_path: str | None = None
    score: float | None = None
    metadata: dict[str, Any] | None = None
```

---

### 7.2 `backend/app/data/chat_models.py`（新增）

**当前作用**
无，新建文件。

**需要新增 ORM 模型**
- `ChatSession`
- `ChatMessage`
- `MessageSource`
- `MessageFeedback`
- `SearchHistory`

**建议字段**

#### `ChatSession`
- `id`
- `title`
- `created_at`
- `updated_at`
- `last_message_at`

#### `ChatMessage`
- `id`
- `session_id`
- `role`
- `content`
- `message_type`
- `retrieval_params_json`
- `created_at`

#### `MessageSource`
- `id`
- `message_id`
- `source_type`
- `source_id`
- `score`
- `title`
- `content_snapshot`
- `file_path`
- `metadata_json`

#### `MessageFeedback`
- `id`
- `message_id`
- `feedback_type`
- `comment`
- `created_at`

#### `SearchHistory`
- `id`
- `query_text`
- `query_type`
- `query_image_path`
- `session_id`
- `created_at`

---

### 7.3 `backend/app/data/models.py`

**当前作用**
保存 `ImageRecord`。

**建议修改**
- 保持 `ImageRecord` 不拆
- 若未来要支持更细过滤，可补充：
  - `source_type`
  - 更规范的 `tags` 存储方式
- 本轮尽量少改，避免影响现有上传链路

**本轮重点**
- 不在这里堆更多模型
- 会话类模型放入 `chat_models.py`

---

### 7.4 `backend/app/data/database.py`

**当前作用**
提供 `engine`、`SessionLocal`、`Base`、`get_db()`。

**建议修改**
- 逻辑基本不变
- 如果新增 JSON 字段在 SQLite 下序列化处理不稳定，可在 service 层先存为字符串 JSON

**重点**
- 保持 `get_db()` 继续作为 router 依赖注入入口

---

### 7.5 `backend/app/main.py`

**当前作用**
注册路由、执行 `Base.metadata.create_all()`。

**建议修改**
- 新增导入：
  - `from .data import chat_models  # noqa: F401`
- 如果拆出新 router 文件，也在这里注册

**目标**
确保新增表可以自动建表。

---

### 7.6 `backend/app/application/chat_service.py`（新增）

**当前作用**
无，新建文件。

**建议职责**
- 创建会话
- 查询会话列表
- 获取会话详情
- 更新会话标题
- 删除会话
- 获取消息历史
- 持久化一轮 user/assistant 消息
- 写入 `message_sources`
- 提交 message feedback

**建议核心函数**
- `create_session(db, title)`
- `list_sessions(db, limit, offset)`
- `get_session(db, session_id)`
- `update_session_title(db, session_id, title)`
- `delete_session(db, session_id)`
- `list_messages(db, session_id)`
- `create_user_message(...)`
- `create_assistant_message(...)`
- `save_message_sources(...)`
- `submit_feedback(...)`

---

### 7.7 `backend/app/application/search_service.py`（新增）

**建议职责**
- 记录文本搜索历史
- 记录图像搜索历史
- 获取搜索历史
- 清空搜索历史
- 根据 `image_id` 发起相似图片检索

**建议核心函数**
- `record_text_search(...)`
- `record_image_search(...)`
- `list_search_history(...)`
- `clear_search_history(...)`
- `find_similar_images(...)`

---

### 7.8 `backend/app/api/routers/chat.py`

**当前作用**
提供 `/api/rag/chat` 和 `/api/rag/chat/stream`，当前 session 是内存实现。

**需要删除/替换的旧逻辑**
- `_chat_sessions`
- `_get_history()`
- `_save_turn()`

**需要新增接口**
- `POST /api/chat/sessions`
- `GET /api/chat/sessions`
- `GET /api/chat/sessions/{session_id}`
- `PATCH /api/chat/sessions/{session_id}`
- `DELETE /api/chat/sessions/{session_id}`
- `GET /api/chat/sessions/{session_id}/messages`
- `POST /api/chat/messages/{message_id}/feedback`

**需要改造接口**
- `POST /api/rag/chat`

**建议改造方式**
- 保留 `/api/rag/chat` 路径不变
- 改为接收 JSON `ChatRequest`
- 通过 DB 中的 session/messages 获取历史，而不是内存字典
- 调用 adapter/service 返回结构化 `ChatResponse`

**流式接口建议**
- 当前 `/api/rag/chat/stream` 先保留
- 第一版可不做消息落库，或只在流结束后一次性落库
- 不建议第一版同时大改普通接口和 SSE 接口

---

### 7.9 `backend/app/api/routers/search.py`

**当前作用**
提供文本检索与图像检索。

**需要增强**
- 文本检索支持 `candidate_k`、`enable_rerank`、`retrieval_scope`、`enable_query_transform`、`score_threshold`、`filters`
- 图像检索支持同类参数
- 记录搜索历史
- 新增相似图片接口

**建议新增接口**
- `GET /api/search/history`
- `DELETE /api/search/history`
- `GET /api/search/images/{image_id}/similar`

---

### 7.10 `backend/app/langchain_integration/adapters.py`

**当前作用**
统一编排上传、检索、RAG。

**需要新增方法**
- `chat_with_session(...)`
- `search_with_options(...)`
- `search_similar_images(...)`
- `build_citation_sources(...)`

**建议职责**
- 如果没有 `session_id`，自动创建会话
- 保存用户消息
- 调用现有 `rag_chat()` / 检索逻辑
- 从检索结果映射 `sources`
- 保存 assistant message
- 保存 `message_sources`
- 返回统一 `ChatResponse`

**优点**
- router 层仍保持很薄
- RAG 编排逻辑集中在 adapter/service 层

---

### 7.11 `backend/app/langchain_integration/retrievers.py`

**当前作用**
已支持 Multi-Query、混合检索、CrossEncoder 精排。

**需要增强**
- 接收 per-request `candidate_k`
- 接收 `enable_rerank`
- 接收 `enable_query_transform`
- 接收 `score_threshold`
- 接收 `filters`
- 预留 `retrieval_scope`

**建议做法**
- 不破坏现有默认行为
- 增加可选参数并沿链路透传

---

### 7.12 `backend/app/langchain_integration/vectorstores.py`

**当前作用**
封装 Chroma，底层已有 `filter` 参数支持。

**需要增强**
- `search_by_text()` 增加 `filters` 参数
- 对过滤对象做一次规范转换
- 返回结果中保留更完整 metadata 供 `sources` 使用

**可复用点**
- `similarity_search_with_score(..., filter=filter)` 已经具备基础能力

---

### 7.13 `backend/app/langchain_integration/query_transform.py`

**当前作用**
用于 Query Rewrite / Expand。

**建议修改**
- 不改核心实现
- 只在上层增加 per-request 控制开关

---

### 7.14 `backend/app/retrieval/rerank.py`

**当前作用**
支持当前重排逻辑。

**建议修改**
- 增加“是否启用 rerank”的上层控制
- 增加阈值截断逻辑（如在 rerank 后按 `score_threshold` 过滤）

---

### 7.15 `backend/tests/`（建议新增）

建议新增：
- `backend/tests/test_chat_sessions.py`
- `backend/tests/test_chat_messages.py`
- `backend/tests/test_chat_feedback.py`
- `backend/tests/test_search_history.py`
- `backend/tests/test_similar_images.py`
- `backend/tests/test_rag_chat_contract.py`

测试重点：
- 会话 CRUD
- 聊天后 user/assistant message 落库
- `sources` 正确返回与保存
- 检索参数是否生效
- 搜索历史是否记录
- feedback 是否写入

---

## 8. 每个接口的请求 / 响应样例

### 8.1 创建会话

**POST** `/api/chat/sessions`

请求：
```json
{
  "title": "毕业设计答辩准备"
}
```

响应：
```json
{
  "id": "0d2a9f77-0b2f-4b2c-a0c2-95a1a1f8b77d",
  "title": "毕业设计答辩准备",
  "created_at": "2026-03-31T12:00:00",
  "updated_at": "2026-03-31T12:00:00",
  "last_message_at": null
}
```

---

### 8.2 获取会话列表

**GET** `/api/chat/sessions?limit=20&offset=0`

响应：
```json
{
  "items": [
    {
      "id": "0d2a9f77-0b2f-4b2c-a0c2-95a1a1f8b77d",
      "title": "毕业设计答辩准备",
      "created_at": "2026-03-31T12:00:00",
      "updated_at": "2026-03-31T12:05:00",
      "last_message_at": "2026-03-31T12:05:00"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

---

### 8.3 获取会话详情

**GET** `/api/chat/sessions/{session_id}`

响应：
```json
{
  "id": "0d2a9f77-0b2f-4b2c-a0c2-95a1a1f8b77d",
  "title": "毕业设计答辩准备",
  "created_at": "2026-03-31T12:00:00",
  "updated_at": "2026-03-31T12:05:00",
  "last_message_at": "2026-03-31T12:05:00"
}
```

---

### 8.4 重命名会话

**PATCH** `/api/chat/sessions/{session_id}`

请求：
```json
{
  "title": "多模态 RAG 功能规划"
}
```

响应：
```json
{
  "id": "0d2a9f77-0b2f-4b2c-a0c2-95a1a1f8b77d",
  "title": "多模态 RAG 功能规划",
  "created_at": "2026-03-31T12:00:00",
  "updated_at": "2026-03-31T12:10:00",
  "last_message_at": "2026-03-31T12:05:00"
}
```

---

### 8.5 删除会话

**DELETE** `/api/chat/sessions/{session_id}`

响应：
```json
{
  "success": true,
  "message": "session deleted"
}
```

---

### 8.6 获取会话消息历史

**GET** `/api/chat/sessions/{session_id}/messages`

响应：
```json
{
  "session_id": "0d2a9f77-0b2f-4b2c-a0c2-95a1a1f8b77d",
  "items": [
    {
      "id": "msg_user_001",
      "role": "user",
      "content": "请总结这个系统还能加什么主流功能？",
      "created_at": "2026-03-31T12:01:00"
    },
    {
      "id": "msg_assistant_001",
      "role": "assistant",
      "content": "建议优先补齐会话管理、消息持久化、引用溯源、检索参数化。",
      "created_at": "2026-03-31T12:01:02"
    }
  ]
}
```

---

### 8.7 多模态 RAG 聊天

**POST** `/api/rag/chat`

请求：
```json
{
  "session_id": "0d2a9f77-0b2f-4b2c-a0c2-95a1a1f8b77d",
  "message": "请结合当前项目，给我设计一个支持历史对话和引用溯源的升级方案。",
  "retrieval": {
    "top_k": 5,
    "candidate_k": 20,
    "enable_rerank": true,
    "retrieval_scope": "mixed",
    "enable_query_transform": true,
    "score_threshold": 0.2,
    "filters": {
      "source_dataset": "custom",
      "status": "Completed",
      "source_type": "image"
    }
  }
}
```

响应：
```json
{
  "session_id": "0d2a9f77-0b2f-4b2c-a0c2-95a1a1f8b77d",
  "message_id": "msg_assistant_002",
  "answer": "建议你优先采用会话化多模态 RAG 后端升级方案，先补齐会话管理、消息持久化、引用溯源和检索参数化。",
  "sources": [
    {
      "source_type": "image",
      "source_id": "img_001",
      "title": null,
      "description": "一张展示系统架构流程的示意图",
      "file_path": "backend/storage/custom/img_001.jpg",
      "score": 0.12,
      "metadata": {
        "source_dataset": "custom",
        "filename": "architecture.jpg"
      }
    },
    {
      "source_type": "document",
      "source_id": "doc_003_chunk_2",
      "title": "毕业设计开发架构与需求说明书",
      "description": "当前系统已支持多模态检索与 RAG 问答，下一步应补齐主流系统功能。",
      "file_path": null,
      "score": 0.18,
      "metadata": {
        "doc_id": "doc_003",
        "chunk_index": 2
      }
    }
  ],
  "retrieval_params": {
    "top_k": 5,
    "candidate_k": 20,
    "enable_rerank": true,
    "retrieval_scope": "mixed",
    "enable_query_transform": true,
    "score_threshold": 0.2
  },
  "created_at": "2026-03-31T12:15:00"
}
```

---

### 8.8 文本到图像检索（增强版）

**POST** `/api/search/text-to-image`

请求：
```json
{
  "query": "系统架构图",
  "top_k": 10,
  "candidate_k": 30,
  "enable_rerank": true,
  "retrieval_scope": "image",
  "enable_query_transform": false,
  "score_threshold": 0.3,
  "filters": {
    "source_dataset": "custom",
    "status": "Completed"
  }
}
```

响应：
```json
{
  "query": "系统架构图",
  "results": [
    {
      "id": "img_001",
      "file_path": "backend/storage/custom/img_001.jpg",
      "description": "展示后端模块与检索链路的系统架构图",
      "score": 0.11
    },
    {
      "id": "img_005",
      "file_path": "backend/storage/custom/img_005.jpg",
      "description": "RAG 检索增强问答系统流程图",
      "score": 0.17
    }
  ],
  "retrieval_params": {
    "top_k": 10,
    "candidate_k": 30,
    "enable_rerank": true,
    "retrieval_scope": "image",
    "enable_query_transform": false,
    "score_threshold": 0.3
  }
}
```

---

### 8.9 图像到图像检索（增强版）

**POST** `/api/search/image-to-image`

请求：
- `multipart/form-data`
- 字段：
  - `file`
  - `top_k=10`
  - `candidate_k=30`
  - `enable_rerank=true`
  - `retrieval_scope=image`

响应：
```json
{
  "query_description": "一张展示系统模块关系的架构图，包含前端、后端、向量库与数据库。",
  "results": [
    {
      "id": "img_008",
      "file_path": "backend/storage/custom/img_008.jpg",
      "description": "系统整体架构图，展示检索和问答流程",
      "score": 0.09
    }
  ],
  "retrieval_params": {
    "top_k": 10,
    "candidate_k": 30,
    "enable_rerank": true,
    "retrieval_scope": "image"
  }
}
```

---

### 8.10 获取搜索历史

**GET** `/api/search/history?limit=20&offset=0`

响应：
```json
{
  "items": [
    {
      "id": "hist_001",
      "query_text": "系统架构图",
      "query_type": "text",
      "query_image_path": null,
      "session_id": "0d2a9f77-0b2f-4b2c-a0c2-95a1a1f8b77d",
      "created_at": "2026-03-31T12:20:00"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

---

### 8.11 清空搜索历史

**DELETE** `/api/search/history`

响应：
```json
{
  "success": true,
  "message": "search history cleared"
}
```

---

### 8.12 相似图片推荐

**GET** `/api/search/images/{image_id}/similar?top_k=10`

响应：
```json
{
  "image_id": "img_001",
  "results": [
    {
      "id": "img_008",
      "file_path": "backend/storage/custom/img_008.jpg",
      "description": "系统整体架构图，展示检索和问答流程",
      "score": 0.09
    },
    {
      "id": "img_013",
      "file_path": "backend/storage/custom/img_013.jpg",
      "description": "知识库管理与检索流程示意图",
      "score": 0.14
    }
  ]
}
```

---

### 8.13 消息反馈

**POST** `/api/chat/messages/{message_id}/feedback`

请求：
```json
{
  "feedback_type": "upvote",
  "comment": "回答结构很清晰，适合作为后端升级路线。"
}
```

响应：
```json
{
  "id": "fb_001",
  "message_id": "msg_assistant_002",
  "feedback_type": "upvote",
  "comment": "回答结构很清晰，适合作为后端升级路线。",
  "created_at": "2026-03-31T12:25:00"
}
```

---

## 9. 推荐实施顺序

### 第 1 批
1. `chat_sessions`
2. `chat_messages`
3. `POST /api/chat/sessions`
4. `GET /api/chat/sessions`
5. `GET /api/chat/sessions/{session_id}/messages`
6. `POST /api/rag/chat` 支持 `session_id`

### 第 2 批
7. `message_sources`
8. `ChatResponse.sources`
9. assistant message 与 sources 落库

### 第 3 批
10. 检索参数化
11. metadata filter
12. similar image

### 第 4 批
13. search history
14. message feedback

---

## 10. 风险与处理建议

### 风险 1：会话上下文注入方式不清晰
建议：
- 第一版先做“消息持久化 + 历史展示”
- 多轮上下文只注入最近 N 轮文本消息
- 暂不引入复杂摘要记忆

### 风险 2：metadata filter 在向量库与 SQL 字段不完全一致
建议：
- 第一版采用“两阶段过滤”
- 先向量召回，再按 SQL 元数据二次过滤

### 风险 3：聊天接口从 multipart 到 JSON 的兼容性
建议：
- 保留旧接口兼容形式
- 新增标准 JSON 接口模型
- 优先保证新接口清晰

---

## 11. 结论

本轮最推荐的正式实现范围：

- 会话管理
- 消息历史
- 聊天持久化
- 引用溯源
- 检索参数化
- 元数据过滤
- 搜索历史
- 问答反馈
- 相似图片接口

这是一套最平衡、最主流、也最适合当前项目阶段的后端升级方案。
