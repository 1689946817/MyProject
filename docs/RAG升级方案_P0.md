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
