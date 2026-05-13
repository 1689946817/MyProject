"""
UniDoc-Bench Baseline CLIP：qwen3-vl-embedding 多模态图像检索。

使用 qwen3-vl-embedding 多模态融合向量模型，将图像直接编码为向量，
查询时将文本编码到同一向量空间，通过余弦相似度进行跨模态检索。

与 Proposed 方法的区别：
- CLIP baseline：直接将原始图像编码为向量（端到端多模态检索）
- Proposed：先用 MLLM 生成文本描述，再用文本 Embedding 检索（两阶段）

集合命名规则：unidoc_{domain}_clip
例如：unidoc_clip_clip、unidoc_healthcare_clip
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

import chromadb
from chromadb.config import Settings as ChromaSettings

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.core.config import settings  # noqa: E402
from app.langchain_integration.models import get_multimodal_embedding_model  # noqa: E402

# 初始化持久化 ChromaDB 客户端
_client = chromadb.Client(
    ChromaSettings(
        is_persistent=True,
        persist_directory=settings.CHROMA_PERSIST_DIR,
    )
)


def _collection_name(domain: str) -> str:
    return f"unidoc_{domain}_clip"


def build_index(domain: str, image_records: List[dict]) -> None:
    """构建图像向量索引（qwen3-vl-embedding）。"""
    embedder = get_multimodal_embedding_model()
    if not hasattr(embedder, "embed_images"):
        raise NotImplementedError("Multimodal embedding model does not support embed_images.")

    valid_records = [r for r in image_records if os.path.exists(r["file_path"])]
    skipped = len(image_records) - len(valid_records)
    if skipped:
        print(f"[SKIP] {skipped} images not found on disk.")
    if not valid_records:
        print("[WARNING] No valid images to process.")
        return

    image_paths = [r["file_path"] for r in valid_records]
    ids = [r["id"] for r in valid_records]
    metadatas = [{"file_path": r["file_path"], "domain": domain, "source": "unidoc_clip"} for r in valid_records]

    print(f"Encoding {len(image_paths)} images with qwen3-vl-embedding...")
    embeddings = embedder.embed_images(image_paths)

    col_name = _collection_name(domain)
    try:
        _client.delete_collection(col_name)
    except Exception:
        pass
    col = _client.get_or_create_collection(name=col_name)
    col.add(embeddings=embeddings, ids=ids, metadatas=metadatas)
    print(f"Index built: {len(ids)} images in '{col_name}'")


def retrieve(query: str, domain: str, top_k: int = 10) -> List[str]:
    """使用 CLIP 方法检索图像。

    将查询文本通过 qwen3-vl-embedding 编码为向量，
    在图像向量库中执行余弦相似度检索。

    Args:
        query: 查询文本。
        domain: 领域名称，决定检索哪个集合。
        top_k: 返回的检索结果数量，默认 10。

    Returns:
        List[str]: top_k 个预测图像 ID 列表。
    """
    import time
    embedder = get_multimodal_embedding_model()
    # embed_query 最多重试 5 次，失败后等待 3 秒重试
    for attempt in range(5):
        try:
            emb = embedder.embed_query(query)
            break
        except Exception as e:
            if attempt == 4:
                raise
            print(f"embed_query failed (attempt {attempt+1}/5): {e}, retrying in 3s...")
            time.sleep(3)
    col = _client.get_or_create_collection(name=_collection_name(domain))
    results = col.query(query_embeddings=[emb], n_results=top_k)
    return [str(i) for i in results.get("ids", [[]])[0]]


def check_index(domain: str) -> bool:
    """检查指定领域的 CLIP 索引是否已构建且非空。

    Args:
        domain: 领域名称。

    Returns:
        bool: True 表示索引包含至少一条记录。
    """
    col = _client.get_or_create_collection(name=_collection_name(domain))
    return col.count() > 0
