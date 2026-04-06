"""
LangChain 适配器模块

该模块提供与现有系统的适配层，包括：
- 与现有 API 路由的适配
- 与现有数据库模型的适配
- 与现有业务逻辑的适配

确保 LangChain 重构后的系统与现有前端、数据库、文件存储等无缝集成。
"""
import base64
import logging
import os
import uuid
from typing import Any, Dict, Iterator, List, Optional, Tuple

from fastapi import UploadFile
from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session

from app.data.doc_models import DocumentRecord
from app.data.models import ImageRecord
from app.data.storage import get_image_path, get_doc_path
from app.core.config import settings
from app.langchain_integration.agentic_rag import classify_chat_intent
from app.langchain_integration.chains import (
    get_image_description_chain,
    get_rag_chain,
    ImageDescriptionChain,
    RAGChain,
)
from app.langchain_integration.doc_parser import parse_pdf
from app.langchain_integration.models import build_image_data_url, get_chat_model, guess_image_mime_type
from app.langchain_integration.retrievers import get_multimodal_retriever
from app.langchain_integration.vectorstores import get_vector_store, get_document_vector_store

logger = logging.getLogger(__name__)


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

            # 增量更新 BM25 索引
            self._bm25_add_document(image_id, description)

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
        fast: bool = False,
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
        documents = await self.retriever.text_to_image_search(query, top_k=top_k, fast=fast)

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
        fast: bool = False,
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
        documents, description = await self.retriever.image_to_image_search(file, top_k=top_k, fast=fast)

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
        chat_history: Optional[List[Tuple[str, str]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """
        RAG 问答（支持多轮对话历史 + Agentic RAG）
        """
        # 如果启用 Agentic RAG，使用 LangGraph 流程
        from app.core.config import settings
        if settings.AGENTIC_RAG_ENABLED:
            return await self._run_agentic_chat(
                query=query,
                top_k=top_k,
                image=image,
                chat_history=chat_history,
            )

        if image is not None:
            answer, documents = await self.rag_chain.ainvoke_with_image(
                query,
                image,
                top_k=top_k,
                chat_history=chat_history,
            )
            return answer, documents, self._build_default_intent(image is not None)

        # 否则使用标准 RAG
        answer, documents = await self.rag_chain.ainvoke(
            {"query": query, "chat_history": chat_history or []}
        )
        return answer, documents, self._build_default_intent(image is not None)

    async def rag_chat_stream(
        self,
        query: str,
        top_k: int = 5,
        image: Optional[UploadFile] = None,
        chat_history: Optional[List[Tuple[str, str]]] = None,
    ):
        """
        RAG 问答流式版本。
        """
        from app.core.config import settings

        if settings.AGENTIC_RAG_ENABLED:
            answer, docs, _intent = await self._run_agentic_chat(
                query=query,
                top_k=top_k,
                image=image,
                chat_history=chat_history,
            )
            for ch in self._iter_answer_chunks(answer):
                yield ch, docs
            return

        if image is not None:
            async for chunk, docs in self.rag_chain.astream_with_image(
                query=query,
                image=image,
                top_k=top_k,
                chat_history=chat_history,
            ):
                yield chunk, docs
            return

        async for chunk, docs in self.rag_chain.astream(
            {"query": query, "chat_history": chat_history or []}
        ):
            yield chunk, docs

    async def _run_agentic_chat(
        self,
        query: str,
        top_k: int,
        image: Optional[UploadFile],
        chat_history: Optional[List[Tuple[str, str]]],
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        """执行带智能意图识别的 Agentic Chat 核心流程。"""
        intent = await classify_chat_intent(query=query, has_uploaded_image=image is not None)
        execution_mode = intent["execution_mode"]

        if execution_mode == "direct_llm":
            answer = await self._answer_directly(query=query, chat_history=chat_history)
            return answer, [], intent

        if execution_mode == "uploaded_image_qa":
            if image is None:
                answer = await self._answer_directly(query=query, chat_history=chat_history)
                return answer, [], {
                    **intent,
                    "reason": "uploaded_image_missing_fallback_to_direct",
                    "confidence": min(float(intent.get("confidence", 0.5)), 0.6),
                }
            answer = await self._answer_with_uploaded_image(
                query=query,
                image=image,
                chat_history=chat_history,
            )
            return answer, [], intent

        if execution_mode == "image_similarity":
            documents = await self._retrieve_images_for_query(query=query, image=image, top_k=top_k)
            answer = self._build_image_only_answer(documents)
            return answer, documents, intent

        if execution_mode == "image_grounded_answer":
            documents = await self._retrieve_images_for_query(query=query, image=image, top_k=top_k)
            answer = await self._answer_with_retrieved_images(
                query=query,
                documents=documents,
                chat_history=chat_history,
            )
            return answer, documents, intent

        if execution_mode == "multimodal_rag":
            if image is not None:
                answer, documents = await self.rag_chain.ainvoke_with_image(
                    query=query,
                    image=image,
                    top_k=top_k,
                    chat_history=chat_history,
                )
            else:
                answer, documents = await self.rag_chain.ainvoke(
                    {"query": query, "chat_history": chat_history or []}
                )
            return answer, documents, intent

        answer = await self._answer_directly(query=query, chat_history=chat_history)
        return answer, [], {
            **intent,
            "execution_mode": "direct_llm",
            "presentation_mode": "direct_answer",
            "use_rag": False,
            "wants_images": False,
            "reason": "unknown_execution_mode_fallback",
        }

    def _iter_answer_chunks(self, answer: str) -> Iterator[str]:
        """将最终答案切成可回放的小块，供流式接口复用。"""
        for ch in answer:
            yield ch

    def _build_default_intent(self, has_uploaded_image: bool) -> Dict[str, Any]:
        """未启用 Agentic 时提供兼容的默认意图元数据。"""
        return {
            "presentation_mode": "rag_answer",
            "execution_mode": "multimodal_rag",
            "use_rag": True,
            "has_uploaded_image": has_uploaded_image,
            "wants_images": has_uploaded_image,
            "confidence": 1.0,
            "reason": "legacy_rag_path",
        }

    async def _answer_directly(
        self,
        query: str,
        chat_history: Optional[List[Tuple[str, str]]] = None,
    ) -> str:
        """不经过知识库检索，直接调用回答模型。"""
        history_text = "\n".join(f"用户：{q}\n助手：{a}" for q, a in (chat_history or [])[-5:])
        prompt = f"""你是一个专业问答助手，请直接回答用户问题。

对话历史：
{history_text}

用户问题：{query}
"""
        model = get_chat_model()
        result = await model._agenerate([HumanMessage(content=prompt)])
        return result.generations[0].message.content

    async def _answer_with_uploaded_image(
        self,
        query: str,
        image: UploadFile,
        chat_history: Optional[List[Tuple[str, str]]] = None,
    ) -> str:
        """只基于用户上传图片本身进行回答。"""
        contents = await image.read()
        await image.seek(0)
        image_b64 = base64.b64encode(contents).decode("utf-8")
        mime_type = image.content_type or guess_image_mime_type(image.filename)
        history_text = "\n".join(f"用户：{q}\n助手：{a}" for q, a in (chat_history or [])[-5:])
        prompt = (
            "你是一个图片问答助手。只基于用户当前上传的图片内容回答问题，"
            "不要引用知识库或臆测图片外信息。如果图片中没有足够信息，请明确说明。"
            f"\n\n对话历史：\n{history_text}\n\n用户问题：{query}"
        )
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": build_image_data_url(image_b64, mime_type)}},
            ]
        )
        model = get_chat_model()
        result = await model._agenerate([message])
        return result.generations[0].message.content

    async def _retrieve_images_for_query(
        self,
        query: str,
        image: Optional[UploadFile],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """根据文本或上传图片检索知识库图片。"""
        if image is not None:
            documents, _description = await self.image_to_image_search(image, top_k=top_k, fast=True)
            return documents
        return await self.text_to_image_search(query, top_k=top_k, fast=True)

    def _build_image_only_answer(self, documents: List[Dict[str, Any]]) -> str:
        """为纯找图请求生成简短说明。"""
        if not documents:
            return "未找到相关图片。"
        return f"为你找到 {len(documents)} 张相关图片。"

    async def _answer_with_retrieved_images(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        chat_history: Optional[List[Tuple[str, str]]] = None,
    ) -> str:
        """基于检索到的图片和相关文本生成回答。"""
        if not documents:
            return "未找到相关图片，暂时无法根据知识库给出可靠回答。"

        max_images = max(1, settings.IMAGE_GROUNDED_MAX_IMAGES)
        max_history_turns = max(0, settings.IMAGE_GROUNDED_MAX_HISTORY_TURNS)
        grounded_documents = documents[:max_images]
        grounded_history = (chat_history or [])[-max_history_turns:] if max_history_turns else []

        text_chunks: List[Dict[str, Any]] = []
        if settings.IMAGE_GROUNDED_TEXT_AUGMENT_ENABLED and settings.IMAGE_GROUNDED_TEXT_TOP_K > 0:
            text_chunks = self.document_vector_store.similarity_search(
                query,
                k=settings.IMAGE_GROUNDED_TEXT_TOP_K,
            )

        return await self.rag_chain.agenerate_from_context(
            query=query,
            documents=grounded_documents,
            text_chunks=text_chunks,
            chat_history=grounded_history,
        )

    def _rebuild_bm25_index(self) -> None:
        """全量重建 BM25 索引（仅用于启动和手动触发）"""
        try:
            from app.retrieval.hybrid import rebuild_bm25_index
            rebuild_bm25_index()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[Adapter] BM25 索引重建失败: {e}")

    def _bm25_add_document(self, doc_id: str, text: str) -> None:
        """增量添加单篇文档到 BM25 索引"""
        try:
            from app.retrieval.hybrid import get_bm25_index
            index = get_bm25_index()
            index.add_document(doc_id, text)
            index.save()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[Adapter] BM25 增量更新失败: {e}")

    def _bm25_add_chunks(self, doc_id: str, text_chunks: List[str], image_count: int) -> None:
        """增量添加 PDF 的文本片段到 BM25 索引"""
        try:
            from app.retrieval.hybrid import get_bm25_index
            index = get_bm25_index()
            for i, chunk in enumerate(text_chunks):
                chunk_id = f"{doc_id}_chunk_{i}"
                index.add_document(chunk_id, chunk)
            if text_chunks or image_count > 0:
                index.save()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[Adapter] BM25 增量更新失败: {e}")

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
                except Exception as exc:
                    logger.warning(
                        "[Adapter] PDF 图片处理失败: file=%s index=%s error=%s",
                        file_name,
                        idx,
                        exc,
                    )

            # 更新文档记录
            record.chunk_count = len(text_chunks)
            record.image_count = processed_image_count
            record.status = "Completed"
            db.commit()
            db.refresh(record)

            # 增量更新 BM25 索引（文本片段 + 图片描述）
            self._bm25_add_chunks(doc_id, text_chunks, processed_image_count)

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
