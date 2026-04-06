"""
BM25 索引管理 + RRF（Reciprocal Rank Fusion）混合检索模块

提供：
- BM25Index：基于 rank_bm25 的关键词检索索引，支持构建/搜索/持久化
- reciprocal_rank_fusion：向量检索与 BM25 检索结果的 RRF 融合
"""
import logging
import os
import pickle
import re
from typing import Any, Dict, List, Optional

from app.application.knowledge_management import load_json_dict
from app.core.config import settings

logger = logging.getLogger(__name__)

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _tokenize(text: str) -> List[str]:
    """中文 jieba 分词 + 英文按词切分，过滤停用词和单字符"""
    text = text.lower()
    try:
        import jieba
        tokens = list(jieba.cut(text))
    except ImportError:
        logger.warning("[BM25] jieba 未安装，退化为正则分词")
        tokens = re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', text)
    # 过滤空白和纯标点
    return [t.strip() for t in tokens if t.strip() and re.search(r'[\u4e00-\u9fff]|[a-zA-Z0-9]', t)]


class BM25Index:
    """BM25 关键词检索索引"""

    def __init__(self, index_path: Optional[str] = None):
        self.index_path = index_path or os.path.join(
            _BACKEND_DIR, settings.BM25_INDEX_PATH,
        )
        self._bm25 = None
        self._doc_ids: List[str] = []
        self._doc_ids_set: set[str] = set()
        self._corpus: List[List[str]] = []

    @property
    def is_ready(self) -> bool:
        return self._bm25 is not None and len(self._doc_ids) > 0

    def build(self, doc_ids: List[str], texts: List[str]) -> None:
        """从文档 ID 和文本列表构建 BM25 索引"""
        from rank_bm25 import BM25Okapi

        self._doc_ids = doc_ids
        self._doc_ids_set = set(doc_ids)
        self._corpus = [_tokenize(t) for t in texts]
        self._bm25 = BM25Okapi(self._corpus)
        logger.info(f"[BM25] 索引构建完成: {len(doc_ids)} 篇文档")

    def add_document(self, doc_id: str, text: str) -> None:
        """增量添加单篇文档到索引（避免全量重建）"""
        from rank_bm25 import BM25Okapi

        if doc_id in self._doc_ids_set:
            return  # 已存在，跳过

        self._doc_ids.append(doc_id)
        self._doc_ids_set.add(doc_id)
        self._corpus.append(_tokenize(text))
        self._bm25 = BM25Okapi(self._corpus)
        logger.debug(f"[BM25] 增量添加文档: {doc_id}, 当前共 {len(self._doc_ids)} 篇")

    def search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """BM25 检索，返回 top_k 结果"""
        if not self.is_ready:
            logger.warning("[BM25] 索引未就绪，返回空结果")
            return []

        tokenized_query = _tokenize(query)
        scores = self._bm25.get_scores(tokenized_query)

        scored_indices = sorted(
            enumerate(scores), key=lambda x: x[1], reverse=True
        )[:top_k]

        results = []
        for idx, score in scored_indices:
            if score > 0:
                results.append({
                    "id": self._doc_ids[idx],
                    "bm25_score": float(score),
                })
        return results

    def save(self) -> None:
        """持久化索引到磁盘"""
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        data = {
            "doc_ids": self._doc_ids,
            "corpus": self._corpus,
        }
        with open(self.index_path, "wb") as f:
            pickle.dump(data, f)
        logger.info(f"[BM25] 索引已保存: {self.index_path}")

    def load(self) -> bool:
        """从磁盘加载索引，成功返回 True"""
        if not os.path.exists(self.index_path):
            logger.info(f"[BM25] 索引文件不存在: {self.index_path}")
            return False
        try:
            from rank_bm25 import BM25Okapi

            with open(self.index_path, "rb") as f:
                data = pickle.load(f)
            self._doc_ids = data["doc_ids"]
            self._doc_ids_set = set(self._doc_ids)
            self._corpus = data["corpus"]
            self._bm25 = BM25Okapi(self._corpus)
            logger.info(f"[BM25] 索引已加载: {len(self._doc_ids)} 篇文档")
            return True
        except Exception as e:
            logger.warning(f"[BM25] 索引加载失败: {e}")
            return False


def rebuild_bm25_index(bm25_index: Optional["BM25Index"] = None) -> "BM25Index":
    """
    从 ChromaDB 全量拉取文档重建 BM25 索引。

    同时拉取图片描述集合和文档文本集合。
    """
    from app.data.database import SessionLocal
    from app.data.doc_models import DocumentRecord
    from app.data.models import ImageRecord
    from app.langchain_integration.vectorstores import get_vector_store, get_document_vector_store

    if bm25_index is None:
        bm25_index = get_bm25_index()

    doc_ids: List[str] = []
    texts: List[str] = []

    with SessionLocal() as db:
        enabled_images = {
            item.id: item
            for item in db.query(ImageRecord).filter(ImageRecord.enabled.is_(True)).all()
        }
        enabled_docs = {
            item.id
            for item in db.query(DocumentRecord).filter(DocumentRecord.enabled.is_(True)).all()
        }

        try:
            image_vs = get_vector_store()
            collection = image_vs.vectorstore._collection
            all_data = collection.get(include=["documents", "metadatas"])
            if all_data and all_data["ids"]:
                for idx, item_id in enumerate(all_data["ids"]):
                    image_record = enabled_images.get(item_id)
                    if image_record is None:
                        continue
                    metadata = {}
                    metadatas = all_data.get("metadatas") or []
                    if idx < len(metadatas):
                        metadata = metadatas[idx] or {}
                    parent_doc_id = load_json_dict(getattr(image_record, "extra_metadata", None)).get("doc_id")
                    if parent_doc_id and parent_doc_id not in enabled_docs:
                        continue
                    doc_ids.append(item_id)
                    texts.append(all_data["documents"][idx])
                logger.info(f"[BM25] 从图片集合拉取 {len(doc_ids)} 条启用内容")
        except Exception as e:
            logger.warning(f"[BM25] 拉取图片集合失败: {e}")

        try:
            doc_vs = get_document_vector_store()
            collection = doc_vs._vectorstore._collection
            all_data = collection.get(include=["documents", "metadatas"])
            if all_data and all_data["ids"]:
                added = 0
                metadatas = all_data.get("metadatas") or []
                for idx, item_id in enumerate(all_data["ids"]):
                    metadata = metadatas[idx] if idx < len(metadatas) else {}
                    doc_id = (metadata or {}).get("doc_id")
                    if doc_id not in enabled_docs:
                        continue
                    doc_ids.append(item_id)
                    texts.append(all_data["documents"][idx])
                    added += 1
                logger.info(f"[BM25] 从文档集合拉取 {added} 条启用内容")
        except Exception as e:
            logger.warning(f"[BM25] 拉取文档集合失败: {e}")

    if doc_ids:
        bm25_index.build(doc_ids, texts)
        bm25_index.save()
    else:
        logger.warning("[BM25] 无文档可索引")

    return bm25_index


def reciprocal_rank_fusion(
    vector_results: List[Dict[str, Any]],
    bm25_results: List[Dict[str, Any]],
    vector_weight: Optional[float] = None,
    bm25_weight: Optional[float] = None,
    k: int = 60,
) -> List[Dict[str, Any]]:
    """
    RRF 融合向量检索和 BM25 检索结果。

    公式：score(d) = Σ weight_i / (k + rank_i(d))
    """
    vector_weight = vector_weight or settings.HYBRID_VECTOR_WEIGHT
    bm25_weight = bm25_weight or settings.HYBRID_BM25_WEIGHT

    rrf_scores: Dict[str, float] = {}
    doc_map: Dict[str, Dict[str, Any]] = {}

    for rank, item in enumerate(vector_results):
        doc_id = item["id"]
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + vector_weight / (k + rank + 1)
        if doc_id not in doc_map:
            doc_map[doc_id] = item

    for rank, item in enumerate(bm25_results):
        doc_id = item["id"]
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + bm25_weight / (k + rank + 1)
        if doc_id not in doc_map:
            doc_map[doc_id] = item

    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

    results = []
    for doc_id in sorted_ids:
        item = dict(doc_map[doc_id])
        item["rrf_score"] = rrf_scores[doc_id]
        results.append(item)

    logger.info(
        f"[RRF] 融合完成: 向量 {len(vector_results)} + BM25 {len(bm25_results)} → {len(results)} 条"
    )
    return results


# 全局 BM25 索引实例
_bm25_index: Optional[BM25Index] = None


def get_bm25_index() -> BM25Index:
    """获取 BM25 索引实例（单例，启动时尝试从磁盘加载）"""
    global _bm25_index
    if _bm25_index is None:
        _bm25_index = BM25Index()
        _bm25_index.load()
    return _bm25_index
