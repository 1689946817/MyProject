"""
LangChain 适配器模块

该模块提供与现有系统的适配层，包括：
- 与现有 API 路由的适配
- 与现有数据库模型的适配
- 与现有业务逻辑的适配

确保 LangChain 重构后的系统与现有前端、数据库、文件存储等无缝集成。
"""
import base64
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.data.doc_models import DocumentRecord
from app.data.models import ImageRecord
from app.data.storage import get_image_path, get_doc_path
from app.langchain_integration.chains import (
    get_image_description_chain,
    get_rag_chain,
    ImageDescriptionChain,
    RAGChain,
)
from app.langchain_integration.doc_parser import parse_pdf
from app.langchain_integration.retrievers import get_multimodal_retriever
from app.langchain_integration.vectorstores import get_vector_store, get_document_vector_store


class LangChainAdapter:
    """
    LangChain 适配器

    提供与现有系统的适配接口，包括：
    - 图像上传处理（替代 description_service）
    - 双路检索（替代 dispatcher）
    - RAG 问答（替代 rag_engine）

    保持与现有 API 路由的接口兼容，内部使用 LangChain 组件实现。
    """

    def __init__(
        self,
        image_description_chain: Optional[ImageDescriptionChain] = None,
        rag_chain: Optional[RAGChain] = None,
    ):
        """
        初始化适配器

        Args:
            image_description_chain: 图像描述 Chain，默认使用全局实例
            rag_chain: RAG Chain，默认使用全局实例
        """
        self.image_description_chain = image_description_chain or get_image_description_chain()
        self.rag_chain = rag_chain or get_rag_chain()
        self.vector_store = get_vector_store()
        self.retriever = get_multimodal_retriever()
        self.document_vector_store = get_document_vector_store()

    async def process_image_upload(
        self,
        db: Session,
        file: UploadFile,
        split: str = "custom",
        source_dataset: Optional[str] = None,
    ) -> Tuple[ImageRecord, str]:
        """
        处理单个图像上传

        替代原有的 description_service.process_image_uploads 功能。

        Args:
            db: 数据库会话
            file: 上传的图像文件
            split: 数据集划分（train/val/test/custom）
            source_dataset: 来源数据集名称

        Returns:
            Tuple[ImageRecord, str]: (图像记录, 生成的描述)
        """
        import uuid

        # 生成唯一 ID
        image_id = str(uuid.uuid4())

        # 读取文件内容
        contents = await file.read()

        # 确定文件扩展名
        filename = file.filename or "image.jpg"
        ext = os.path.splitext(filename)[1].lower()
        if not ext:
            ext = ".jpg"

        # 构建存储路径
        storage_path = str(get_image_path(image_id, split))
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)

        # 保存文件
        with open(storage_path, "wb") as f:
            f.write(contents)

        # 创建数据库记录
        record = ImageRecord(
            id=image_id,
            file_path=storage_path,
            source_dataset=source_dataset,
            status="Processing",
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        try:
            # 使用 LangChain Chain 生成描述
            b64_image = base64.b64encode(contents).decode("utf-8")
            description = await self.image_description_chain.ainvoke({
                "image_b64": b64_image,
            })

            # 更新数据库记录
            record.generated_description = description
            record.status = "Completed"
            db.commit()
            db.refresh(record)

            # 写入向量存储
            self.vector_store.upsert_image_description(
                doc_id=image_id,
                text=description,
                metadata={
                    "id": image_id,
                    "file_path": storage_path,
                    "filename": filename,
                    "split": split,
                    "source_dataset": source_dataset,
                },
            )

            # 更新 BM25 索引
            self._rebuild_bm25_index()

            return record, description

        except Exception as e:
            # 更新状态为失败
            record.status = "Failed"
            db.commit()
            raise e

    async def process_image_uploads(
        self,
        db: Session,
        files: List[UploadFile],
        split: str = "custom",
        source_dataset: Optional[str] = None,
    ) -> List[Tuple[ImageRecord, str]]:
        """
        处理多个图像上传

        替代原有的 description_service.process_image_uploads 功能。

        Args:
            db: 数据库会话
            files: 上传的图像文件列表
            split: 数据集划分
            source_dataset: 来源数据集名称

        Returns:
            List[Tuple[ImageRecord, str]]: (图像记录, 描述) 列表
        """
        results = []
        for file in files:
            result = await self.process_image_upload(
                db=db,
                file=file,
                split=split,
                source_dataset=source_dataset,
            )
            results.append(result)
        return results

    async def text_to_image_search(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        文本到图像检索

        替代原有的 dispatcher.text_to_image_search 功能。

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            List[Dict[str, Any]]: 检索结果列表
        """
        documents = await self.retriever.text_to_image_search(query, top_k=top_k)

        # 转换为字典格式
        results = []
        for doc in documents:
            results.append({
                "id": doc.metadata.get("id", ""),
                "document": doc.page_content,
                "metadata": doc.metadata,
                "score": doc.metadata.get("score", 0.0),
            })

        return results

    async def image_to_image_search(
        self,
        file: UploadFile,
        top_k: int = 10,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        图像到图像检索

        替代原有的 dispatcher.image_to_image_search 功能。

        Args:
            file: 上传的图像文件
            top_k: 返回结果数量

        Returns:
            Tuple[List[Dict], str]: (检索结果列表, 生成的描述)
        """
        documents, description = await self.retriever.image_to_image_search(file, top_k=top_k)

        # 转换为字典格式
        results = []
        for doc in documents:
            results.append({
                "id": doc.metadata.get("id", ""),
                "document": doc.page_content,
                "metadata": doc.metadata,
                "score": doc.metadata.get("score", 0.0),
            })

        return results, description

    async def rag_chat(
        self,
        query: str,
        top_k: int = 5,
        image: Optional[UploadFile] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        RAG 问答

        替代原有的 rag_engine.rag_chat 功能。

        Args:
            query: 用户问题
            top_k: 检索结果数量
            image: 可选的查询图像

        Returns:
            Tuple[str, List[Dict]]: (生成的回答, 检索结果列表)
        """
        if image is not None:
            # 图像查询
            return await self.rag_chain.ainvoke_with_image(query, image, top_k=top_k)
        else:
            # 文本查询
            return await self.rag_chain.ainvoke({"query": query})

    def _rebuild_bm25_index(self) -> None:
        """重建 BM25 全量索引"""
        try:
            from app.retrieval.hybrid import rebuild_bm25_index
            rebuild_bm25_index()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[Adapter] BM25 索引重建失败: {e}")

    def get_vector_store_stats(self) -> Dict[str, Any]:
        """
        获取向量存储统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        try:
            collection = self.vector_store.vectorstore._collection
            count = collection.count()
            return {
                "total_documents": count,
                "collection_name": self.vector_store.collection_name,
                "persist_directory": self.vector_store.persist_directory,
            }
        except Exception as e:
            return {
                "error": str(e),
                "collection_name": self.vector_store.collection_name,
            }

    async def process_pdf_upload(self, db: Session, file: UploadFile) -> DocumentRecord:
        """
        处理 PDF 文档上传：解析文本和图片，分别向量化存储。

        流程：
        1. 保存 PDF 文件到 storage/docs/
        2. 创建 DocumentRecord（status=Processing）
        3. 解析 PDF：提取文本片段 + 图片字节
        4. 文本片段 → DocumentVectorStore（documents_text）
        5. 图片字节 → 逐张调用 ImageDescriptionChain → ChromaVectorStore（images_main_kb）
        6. 更新 DocumentRecord status=Completed

        Args:
            db: 数据库会话
            file: 上传的 PDF 文件

        Returns:
            DocumentRecord: 文档记录
        """
        doc_id = str(uuid.uuid4())
        contents = await file.read()
        file_name = file.filename or "document.pdf"

        # 保存 PDF 文件
        doc_path = get_doc_path(doc_id)
        with open(str(doc_path), "wb") as f:
            f.write(contents)

        # 创建数据库记录
        record = DocumentRecord(
            id=doc_id,
            file_name=file_name,
            file_path=str(doc_path),
            status="Processing",
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        try:
            # 解析 PDF
            text_chunks, image_bytes_list = parse_pdf(contents)

            # 文本片段向量化
            if text_chunks:
                self.document_vector_store.upsert_chunks(
                    doc_id=doc_id,
                    chunks=text_chunks,
                    metadatas=[{"file_name": file_name}] * len(text_chunks),
                )

            # 图片向量化（复用图片上传流程）
            processed_image_count = 0
            for idx, img_bytes in enumerate(image_bytes_list):
                try:
                    img_id = str(uuid.uuid4())
                    # 保存图片到 storage/images/custom/
                    from app.data.storage import BASE_STORAGE_DIR
                    img_dir = BASE_STORAGE_DIR / "custom"
                    img_dir.mkdir(parents=True, exist_ok=True)
                    img_path = img_dir / f"{img_id}.jpg"
                    with open(str(img_path), "wb") as f:
                        f.write(img_bytes)

                    # 调用 MLLM 生成描述
                    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
                    description = await self.image_description_chain.ainvoke(
                        {"image_b64": img_b64}
                    )

                    # 写入图片向量存储
                    from langchain_core.documents import Document as LCDoc
                    lc_doc = LCDoc(
                        page_content=description,
                        metadata={
                            "id": img_id,
                            "source": "pdf",
                            "doc_id": doc_id,
                            "file_name": file_name,
                        },
                    )
                    self.vector_store.add_documents([lc_doc], ids=[img_id])

                    # 写入 SQLite image_records
                    from app.data.models import ImageRecord
                    img_record = ImageRecord(
                        id=img_id,
                        file_path=str(img_path),
                        generated_description=description,
                        status="Completed",
                        source_dataset="pdf",
                        extra_metadata=f'{{"doc_id": "{doc_id}"}}',
                    )
                    db.add(img_record)
                    db.commit()

                    processed_image_count += 1
                except Exception:
                    pass

            # 更新文档记录
            record.chunk_count = len(text_chunks)
            record.image_count = processed_image_count
            record.status = "Completed"
            db.commit()
            db.refresh(record)

            # 更新 BM25 索引
            self._rebuild_bm25_index()

        except Exception as e:
            record.status = "Failed"
            record.extra_metadata = str(e)
            db.commit()
            db.refresh(record)

        return record


# 全局适配器实例缓存
_adapter: Optional[LangChainAdapter] = None


def get_langchain_adapter() -> LangChainAdapter:
    """
    获取 LangChain 适配器实例（单例模式）

    Returns:
        LangChainAdapter: 适配器实例
    """
    global _adapter
    if _adapter is None:
        _adapter = LangChainAdapter()
    return _adapter
