# RAG 系统 P0 升级计划

## 背景与目标

当前后端 RAG 系统存在三个核心缺陷：
1. 查询直接向量化，无任何预处理，模糊/复杂 query 召回率低
2. `simple_rerank` 仅按 Chroma 距离排序，不是真正的重排序，精度无保障
3. 仅有向量检索，缺少关键词检索，无法捕获精确词汇匹配

本次升级实施 P0 三项：**查询重写（Multi-Query）、本地 CrossEncoder 重排序、BM25+向量混合检索（RRF融合）**，同时重建 BM25 全量索引。

## 用户确认的选项

| 选项 | 确认值 |
|------|--------|
| 重排序方案 | 本地 FlagEmbedding CrossEncoder（无需 API）|
| BM25 索引范围 | 重建全量索引 |
| 升级范围 | 仅 P0 |
| 语义分块（P2）| 不纳入 |

---

## 涉及文件

### 新建文件
- `backend/app/langchain_integration/query_transform.py` — 查询重写 + Multi-Query 扩展
- `backend/app/retrieval/hybrid.py` — BM25 索引管理 + RRF 融合

### 修改文件
- `backend/app/retrieval/rerank.py` — 升级为本地 FlagEmbedding CrossEncoder 重排序
- `backend/app/langchain_integration/retrievers.py` — 接入混合检索 + 查询重写
- `backend/app/langchain_integration/adapters.py` — 文档入库时同步构建 BM25 索引
- `backend/app/core/config.py` — 新增配置项
- `backend/.env` — 新增环境变量
- `backend/requirements.txt` — 新增依赖

---

## 详细实现方案

### 1. 查询重写 / Multi-Query（`query_transform.py`）

新建 `backend/app/langchain_integration/query_transform.py`：

- 使用 `get_chat_model()` 复用现有 LLM 实例（`models.py:get_chat_model`）
- `QueryRewriter.rewrite(query)` — LLM 改写为检索友好表达
- `QueryRewriter.expand(query, n=3)` — 生成 n 个不同角度的子查询，返回 `[原始query] + [n个子查询]`
- Multi-Query 生成后，每个子查询独立检索，按 doc_id 去重后合并结果
- 配置项 `QUERY_REWRITE_ENABLED`（默认 true）和 `QUERY_MULTI_QUERY_COUNT`（默认 3）

### 2. 本地 CrossEncoder 重排序（`rerank.py`）

替换 `backend/app/retrieval/rerank.py` 中的 `simple_rerank`：

- 使用 `FlagEmbedding.FlagReranker`，模型 `BAAI/bge-reranker-base`（轻量，中英双语）
- 配置项 `RERANK_MODEL_NAME` 可覆盖模型名
- 批量构建 `(query, doc)` 对打分，按分数降序返回 top_k
- 保留 `simple_rerank` 作为 fallback（FlagEmbedding 未安装时降级）
- 检索流程：**初检 top-20 → CrossEncoder 精排 → 返回 top-K**

### 3. BM25 + 向量混合检索 RRF（`hybrid.py`）

新建 `backend/app/retrieval/hybrid.py`：

- `BM25Index` 类：使用 `rank_bm25.BM25Okapi`，支持 `build / search / save / load`
- BM25 索引持久化路径：`BM25_INDEX_PATH`（默认 `storage/bm25_index.pkl`）
- `reciprocal_rank_fusion(vector_results, bm25_results, vector_weight=0.6, k=60)` — RRF 融合
- RRF 公式：`score(d) = Σ weight_i / (k + rank_i(d))`
- `rebuild_bm25_index()` — 从 ChromaDB 全量拉取文档重建索引

### 4. 修改 `retrievers.py` — 接入三项能力

`MultimodalRetriever` 文本检索流程改造：
```
原始 query
  → QueryRewriter.expand() 生成 3 个子查询
  → 每个子查询并行执行混合检索（向量+BM25，RRF融合）
  → 多查询结果按 doc_id 去重合并（取最高分）
  → top-20 候选送入 CrossEncoderReranker
  → 返回 top-K
```
文档检索路径（`DocumentVectorStore`）同样接入查询重写和混合检索。

### 5. 修改 `adapters.py` — 入库时更新 BM25 索引

- 在 `process_document_upload()` 完成向量入库后，追加调用 `BM25Index.rebuild()` 全量重建
- 新增管理端点 `POST /api/admin/rebuild-bm25`，用于手动重建全量 BM25 索引（处理历史文档）

### 6. 新增配置项（`config.py` + `.env`）

```python
# 查询重写
QUERY_REWRITE_ENABLED: bool = True
QUERY_MULTI_QUERY_COUNT: int = 3

# 重排序
RERANK_MODEL_NAME: str = "BAAI/bge-reranker-base"
RERANK_TOP_K: int = 5          # 重排后返回数量
RERANK_CANDIDATE_K: int = 20   # 初检候选数量

# 混合检索
BM25_INDEX_PATH: str = "storage/bm25_index.pkl"
HYBRID_VECTOR_WEIGHT: float = 0.6
HYBRID_BM25_WEIGHT: float = 0.4
```

---

## 新增依赖

```
rank-bm25>=0.2.2
FlagEmbedding>=1.2.0
```

---

## 实施顺序

1. 新增配置项（`config.py`）
2. 新建 `hybrid.py`（BM25 索引 + RRF）
3. 升级 `rerank.py`（CrossEncoder，保留 simple_rerank fallback）
4. 新建 `query_transform.py`（查询重写）
5. 修改 `retrievers.py`（接入三项能力）
6. 修改 `adapters.py`（入库时更新 BM25）
7. 新增 `/api/admin/rebuild-bm25` 管理端点
8. 更新 `requirements.txt`
9. 手动调用重建接口，建立历史文档 BM25 索引

---

## 验证方案

1. `pip install rank-bm25 FlagEmbedding` 确认依赖安装
2. 调用 `POST /api/admin/rebuild-bm25` 重建全量 BM25 索引，检查 `storage/bm25_index.pkl` 生成
3. 调用 `POST /api/rag/chat` 发送模糊查询，观察后端日志中：
   - 改写后的子查询内容
   - 混合检索结果（向量+BM25 各自的 top-20）
   - RRF 融合后的排序
   - CrossEncoder 精排后的 top-5
4. 对比升级前后同一查询的检索结果质量





RAG 系统优化方案

 背景

 P0 升级（Multi-Query、BM25+向量混合检索 RRF、CrossEncoder 重排序）已完成。本方案基于两份参考文档（17种RAG方案 +
 RAG系统完整指南）和代码审计结果，提出分层优化计划。

 ---
 P1: 关键 Bug 修复（基础质量保障）

 P1-1: 修复 RAGChain 双重检索

 - 问题：chains.py 的 invoke()/ainvoke() 先显式调用 search_with_dict_output()，然后 LCEL chain 内部的 retrieve_runnable 又调用一次，每次 RAG 请求执行 2    
 次完整检索
 - 方案：检索只做一次，将预检索结果直接传入 chain，跳过内部检索
 - 文件：backend/app/langchain_integration/chains.py

 P1-2: 修复 RAG Chat 缺失 Multi-Query 扩展

 - 问题：search_with_dict_output() 是同步方法，直接调 _hybrid_search_sync()，完全跳过了 _multi_query_hybrid_search()。RAG
 聊天（主功能）的检索质量低于搜索接口
 - 方案：新增 async_search_with_dict_output() 走完整异步管线；RAGChain.ainvoke() 改用异步检索
 - 文件：backend/app/langchain_integration/retrievers.py, chains.py

 P1-3: 修复多个 Adapter 实例

 - 问题：chat.py、search.py、kb.py 各自 adapter = LangChainAdapter() 创建独立实例，未使用单例
 - 方案：统一改为 get_langchain_adapter() 或 FastAPI 依赖注入
 - 文件：backend/app/api/routers/chat.py, search.py, kb.py

 P1-4: 修复中文 BM25 分词

 - 问题：hybrid.py 的 _tokenize() 将中文按单字拆分（['自','然','风','景']），严重降低 BM25 精度
 - 方案：引入 jieba 分词，改后需重建 BM25 索引
 - 文件：backend/app/retrieval/hybrid.py, requirements.txt

 ---
 P2: 高影响力功能升级

 P2-1: 语义分块（替代字符硬切分）

 - 现状：doc_parser.py 按 500 字符滑动窗口切分，会截断句子和语义
 - 方案：按句子边界（。！？\n\n）切分后合并至 chunk_size，保证语义完整性
 - 参考：17种方案 #2 语义切分（GPT-4 评分 0.5）
 - 文件：backend/app/langchain_integration/doc_parser.py, core/config.py

 P2-2: 上下文压缩（LLM 过滤噪声）

 - 现状：检索到的所有文档原文直接拼接送入 LLM，包含大量无关内容
 - 方案：在重排序后、生成前，用 LLM 提取每个文档中与 query 相关的部分，过滤无关内容
 - 参考：17种方案 #10 上下文压缩（GPT-4 评分 0.75）
 - 新文件：backend/app/langchain_integration/context_compression.py
 - 修改：chains.py

 P2-3: 流式响应（SSE）

 - 现状：RAG 聊天等待完整生成后才返回，用户体验差（10-30秒空白）
 - 方案：MultimodalChatModel 增加 _astream_generate()；新增 POST /api/rag/chat/stream SSE 端点；前端用 EventSource 消费
 - 文件：models.py, chains.py, chat.py, 前端 Chat.vue, chat.ts

 P2-4: 对话记忆（多轮聊天）

 - 现状：每次聊天独立，无上下文。用户问"这张图是什么"后追问"红色物体是什么"无法关联
 - 方案：前端生成 session_id，后端维护内存会话历史（最近 N 轮），历史参与查询重写和 Prompt 构建
 - 文件：chains.py, chat.py, schemas.py, 前端 Chat.vue, chat.ts

 P2-5: BM25 增量更新

 - 现状：每次上传图片/文档都全量重建 BM25 索引（从 ChromaDB 拉取所有文档），O(N) per insert
 - 方案：新增 BM25Index.add_document() 方法，追加到语料后重构 BM25Okapi 对象（避免 ChromaDB 全扫描）；全量重建仅在启动和手动触发时执行
 - 文件：backend/app/retrieval/hybrid.py, adapters.py

 P2-6: 并行子查询执行

 - 现状：_multi_query_hybrid_search 中 3 个子查询串行执行，延迟 3x
 - 方案：用 asyncio.gather() + asyncio.to_thread() 并行执行
 - 文件：backend/app/langchain_integration/retrievers.py

 ---
 P3: Agentic RAG 架构升级（核心亮点）

 P3-1: 基于 LangGraph 的 Agentic RAG

 将固定管线 RAGChain 升级为自适应、自纠错的智能体 RAG。融合 CRAG（纠错检索）+ Self-RAG（自反思生成）+ Adaptive RAG（查询路由）。

 新增依赖：langgraph>=0.2.0

 状态定义

 class AgenticRAGState(TypedDict):
     query: str                    # 原始查询
     rewritten_query: str          # 重写后查询
     sub_queries: List[str]        # Multi-Query 扩展
     retrieved_docs: List[Dict]    # 检索结果
     retrieval_grade: str          # "sufficient" | "insufficient" | "off_topic"
     generation: str               # 生成的回答
     generation_grade: str         # "grounded" | "hallucinated" | "not_useful"
     retry_count: int              # 重试计数（上限 2）
     chat_history: List[Dict]      # 对话历史

 节点（Nodes）

 ┌───────────────────┬──────────────────────────────────────────────────────────────┬─────────────────┐
 │       节点        │                             功能                             │    对应策略     │
 ├───────────────────┼──────────────────────────────────────────────────────────────┼─────────────────┤
 │ route_query       │ LLM 分类查询类型：factual_kb / conversational / out_of_scope │ Adaptive RAG    │
 ├───────────────────┼──────────────────────────────────────────────────────────────┼─────────────────┤
 │ rewrite_query     │ 复用 QueryRewriter，结合对话历史解析代词                     │ Query Transform │
 ├───────────────────┼──────────────────────────────────────────────────────────────┼─────────────────┤
 │ retrieve          │ 调用现有 MultimodalRetriever 完整管线                        │ 混合检索+重排   │
 ├───────────────────┼──────────────────────────────────────────────────────────────┼─────────────────┤
 │ grade_retrieval   │ LLM 逐文档评估相关性，<2 篇相关则判定 insufficient           │ CRAG            │
 ├───────────────────┼──────────────────────────────────────────────────────────────┼─────────────────┤
 │ transform_query   │ 检索不足时从不同角度重新构造查询                             │ CRAG            │
 ├───────────────────┼──────────────────────────────────────────────────────────────┼─────────────────┤
 │ generate          │ 构建多模态 Prompt + 上下文压缩 + MLLM 生成                   │ RAG 生成        │
 ├───────────────────┼──────────────────────────────────────────────────────────────┼─────────────────┤
 │ grade_generation  │ LLM 评估：回答是否有依据？是否有用？                         │ Self-RAG        │
 ├───────────────────┼──────────────────────────────────────────────────────────────┼─────────────────┤
 │ fallback_generate │ 重试耗尽后承认信息不足                                       │ 兜底            │
 └───────────────────┴──────────────────────────────────────────────────────────────┴─────────────────┘

 状态转移图

 START → route_query
   ├─ "conversational" → generate（仅用历史，不检索）→ END
   ├─ "out_of_scope" → fallback_generate → END
   └─ "factual_kb" → rewrite_query → retrieve → grade_retrieval
                                                   ├─ "sufficient" → generate → grade_generation
                                                   │                              ├─ "grounded" + "useful" → END
                                                   │                              ├─ "hallucinated" & retry<2 → transform_query → retrieve
                                                   │                              └─ else → END（返回最佳尝试）
                                                   ├─ "insufficient" & retry<2 → transform_query → retrieve
                                                   └─ "insufficient" & retry>=2 → generate（用现有结果）

 评估器 Prompts（graders.py）

 RETRIEVAL_GRADER = "判断文档是否与查询相关。只回答 YES 或 NO。"
 HALLUCINATION_GRADER = "判断回答是否完全基于上下文。只回答 YES 或 NO。"
 ANSWER_GRADER = "判断回答是否有效回应了问题。只回答 YES 或 NO。"

 集成方式

 - 新文件：agentic_rag.py（LangGraph 状态机）、graders.py（评估器）
 - 配置：AGENTIC_RAG_ENABLED: bool = False，开启后 get_rag_chain() 返回 AgenticRAGChain
 - 接口兼容：AgenticRAGChain 暴露与 RAGChain 相同的 invoke/ainvoke/astream 接口
 - 支持 A/B 对比：通过配置开关在固定管线和 Agentic 管线间切换

 P3-2: 评估框架扩展

 - 新增 --method proposed_agentic 评估方法
 - 新增指标：重试率、平均 LLM 调用次数、接地率（通过幻觉检查的比例）
 - 复用现有 6 个 LLM-as-judge 评估器直接评估 Agentic RAG 输出
 - 文件：evaluation/methods/, evaluation/run_offline_eval.py, evaluation/run_rag_generation.py

 ---
 依赖关系与实施顺序

 阶段 1（并行）: P1-1, P1-2, P1-3, P1-4
 阶段 2（并行）: P2-5, P2-6, P2-1
 阶段 3（顺序）: P2-2 → P2-4
 阶段 4: P2-3（流式响应）
 阶段 5: P3-1（Agentic RAG）
 阶段 6: P3-2（评估扩展）

 验证策略

 - P1：日志确认检索仅执行一次、Multi-Query 在 RAG Chat 中生效、jieba 分词正确、单例实例唯一
 - P2：PDF 分块不截断句子、压缩后 token 数减少、SSE 事件逐步到达、多轮对话上下文连贯、批量上传延迟下降、子查询并行延迟降低
 - P3：用现有评估框架对比 proposed vs proposed_agentic 的 Recall@K、MRR、mAP 和 6 项 LLM 评分；记录 Agent 决策轨迹用于论文分析
