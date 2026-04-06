"""
LangChain 集成测试

测试 LangChain 重构后的完整流程，包括：
- 图像描述生成
- 向量存储操作
- 检索功能
- RAG 问答流程
"""
import base64
import asyncio
import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from types import ModuleType

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "langchain_chroma" not in sys.modules:
    langchain_chroma = ModuleType("langchain_chroma")
    langchain_chroma.Chroma = MagicMock()
    sys.modules["langchain_chroma"] = langchain_chroma

if "fastapi" not in sys.modules:
    fastapi = ModuleType("fastapi")

    class UploadFile:  # pragma: no cover - test import shim
        pass

    fastapi.UploadFile = UploadFile
    sys.modules["fastapi"] = fastapi

if "fitz" not in sys.modules:
    sys.modules["fitz"] = ModuleType("fitz")

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

from app.langchain_integration.chains import ImageDescriptionChain, RAGChain
from app.langchain_integration.vectorstores import ChromaVectorStore
from app.langchain_integration.retrievers import MultimodalRetriever
from app.langchain_integration.adapters import LangChainAdapter
from app.langchain_integration.agentic_rag import classify_chat_intent, generate_answer
from app.langchain_integration.context_compression import compress_context
from app.retrieval.rerank import cross_encoder_rerank


class TestImageDescriptionChain(unittest.TestCase):
    """测试图像描述生成 Chain"""

    def setUp(self):
        """测试前准备"""
        self.mock_model = MagicMock()
        self.chain = ImageDescriptionChain(chat_model=self.mock_model)

    def test_build_chain(self):
        """测试 Chain 构建"""
        self.assertIsNotNone(self.chain._chain)

    def test_invoke(self):
        """测试同步调用"""
        # 模拟模型响应
        mock_result = MagicMock()
        mock_result.content = "A beautiful sunset over the ocean"
        self.mock_model.invoke.return_value = mock_result

        # 调用 Chain
        image_b64 = base64.b64encode(b"fake_image").decode("utf-8")
        result = self.chain.invoke({"image_b64": image_b64})

        # 验证结果
        self.assertEqual(result, "A beautiful sunset over the ocean")

    async def test_ainvoke(self):
        """测试异步调用"""
        # 模拟模型响应
        mock_result = MagicMock()
        mock_result.content = "A cat sitting on a couch"
        self.mock_model.ainvoke = AsyncMock(return_value=mock_result)

        # 调用 Chain
        image_b64 = base64.b64encode(b"fake_image").decode("utf-8")
        result = await self.chain.ainvoke({"image_b64": image_b64})

        # 验证结果
        self.assertEqual(result, "A cat sitting on a couch")


class TestChromaVectorStore(unittest.TestCase):
    """测试 Chroma 向量存储"""

    def setUp(self):
        """测试前准备"""
        # 创建临时目录
        self.temp_dir = tempfile.mkdtemp()

        # 模拟嵌入模型
        self.mock_embedding = MagicMock()
        self.mock_embedding.embed_documents.return_value = [[0.1, 0.2, 0.3]]
        self.mock_embedding.embed_query.return_value = [0.1, 0.2, 0.3]

        with patch("app.langchain_integration.vectorstores.get_embedding_model", return_value=self.mock_embedding):
            with patch("app.core.config.settings.CHROMA_PERSIST_DIR", self.temp_dir):
                with patch("app.core.config.settings.MAIN_IMAGE_COLLECTION_NAME", "test_collection"):
                    self.vector_store = ChromaVectorStore()

    def tearDown(self):
        """测试后清理"""
        # 删除临时目录
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_texts(self):
        """测试添加文本"""
        texts = ["Test document"]
        metadatas = [{"id": "test-1"}]

        ids = self.vector_store.add_texts(texts, metadatas=metadatas)

        self.assertEqual(len(ids), 1)

    def test_similarity_search(self):
        """测试相似度搜索"""
        # 先添加文档
        texts = ["Test document about cats"]
        metadatas = [{"id": "test-1", "file_path": "/path/to/cat.jpg"}]
        self.vector_store.add_texts(texts, metadatas=metadatas)

        # 搜索
        results = self.vector_store.similarity_search("cats", k=1)

        self.assertEqual(len(results), 1)

    def test_upsert_image_description(self):
        """测试更新/插入图像描述"""
        doc_id = "image-123"
        text = "A beautiful sunset"
        metadata = {"file_path": "/path/to/sunset.jpg"}

        self.vector_store.upsert_image_description(doc_id, text, metadata)

        # 验证可以搜索到
        results = self.vector_store.search_by_text("sunset", top_k=1)
        self.assertEqual(len(results), 1)

    def test_search_by_text(self):
        """测试基于文本搜索"""
        # 添加文档
        doc_id = "image-456"
        text = "A dog playing in the park"
        metadata = {"file_path": "/path/to/dog.jpg"}
        self.vector_store.upsert_image_description(doc_id, text, metadata)

        # 搜索
        results = self.vector_store.search_by_text("dog", top_k=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], doc_id)


class TestMultimodalRetriever(unittest.TestCase):
    """测试多模态检索器"""

    def setUp(self):
        """测试前准备"""
        self.mock_vector_store = MagicMock()
        self.mock_chat_model = MagicMock()

        self.retriever = MultimodalRetriever(
            vector_store=self.mock_vector_store,
            chat_model=self.mock_chat_model,
            top_k=5,
        )

    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.retriever.top_k, 5)
        self.assertEqual(self.retriever.vector_store, self.mock_vector_store)
        self.assertEqual(self.retriever.chat_model, self.mock_chat_model)

    def test_text_to_image_search(self):
        """测试文本到图像检索"""
        mock_hit = {
            "id": "img-1",
            "document": "A cat sitting on a table",
            "metadata": {"id": "img-1", "file_path": "/path/to/cat.jpg"},
            "rerank_score": 0.9,
        }

        with patch(
            "app.langchain_integration.retrievers._multi_query_hybrid_search",
            AsyncMock(return_value=[mock_hit]),
        ):
            results = asyncio.run(self.retriever.text_to_image_search("cat", top_k=1))

        # 验证结果
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].page_content, "A cat sitting on a table")

    def test_text_to_image_search_fast_path_uses_configured_candidate_k(self):
        """测试图片快检索路径读取配置的 candidate_k 并关闭 query rewrite"""
        mock_hit = {
            "id": "img-fast",
            "document": "Fast image result",
            "metadata": {"id": "img-fast"},
            "rerank_score": 0.9,
        }

        with patch("app.langchain_integration.retrievers.settings.IMAGE_FAST_RETRIEVAL_ENABLED", True):
            with patch("app.langchain_integration.retrievers.settings.IMAGE_FAST_RETRIEVAL_CANDIDATE_K", 9):
                with patch(
                    "app.langchain_integration.retrievers._multi_query_hybrid_search",
                    AsyncMock(return_value=[mock_hit]),
                ) as mock_search:
                    results = asyncio.run(self.retriever.text_to_image_search("cat", top_k=2, fast=True))

        self.assertEqual(len(results), 1)
        mock_search.assert_awaited_once_with(
            "cat",
            self.mock_vector_store,
            9,
            enable_query_rewrite=False,
        )

    def test_text_to_image_search_fast_path_can_be_disabled_by_config(self):
        """测试关闭配置后 fast=True 也会回退到完整检索路径"""
        mock_hit = {
            "id": "img-full",
            "document": "Full retrieval result",
            "metadata": {"id": "img-full"},
            "rerank_score": 0.9,
        }

        with patch("app.langchain_integration.retrievers.settings.IMAGE_FAST_RETRIEVAL_ENABLED", False):
            with patch("app.langchain_integration.retrievers.settings.RERANK_CANDIDATE_K", 20):
                with patch(
                    "app.langchain_integration.retrievers._multi_query_hybrid_search",
                    AsyncMock(return_value=[mock_hit]),
                ) as mock_search:
                    results = asyncio.run(self.retriever.text_to_image_search("cat", top_k=2, fast=True))

        self.assertEqual(len(results), 1)
        mock_search.assert_awaited_once_with(
            "cat",
            self.mock_vector_store,
            20,
            enable_query_rewrite=True,
        )

    async def test_image_to_image_search(self):
        """测试图像到图像检索"""
        # 模拟模型生成描述
        self.mock_chat_model.agenerate_description = AsyncMock(return_value="A dog in the park")

        # 模拟向量存储返回结果
        mock_doc = Document(
            page_content="A dog playing fetch",
            metadata={"id": "img-2", "file_path": "/path/to/dog.jpg", "score": 0.85},
        )
        self.mock_vector_store.similarity_search_with_score.return_value = [(mock_doc, 0.85)]

        # 创建模拟 UploadFile
        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b"fake_image_data")

        # 调用检索
        results, description = await self.retriever.image_to_image_search(mock_file, top_k=1)

        # 验证结果
        self.assertEqual(description, "A dog in the park")
        self.assertEqual(len(results), 1)


class TestRAGChain(unittest.TestCase):
    """测试 RAG Chain"""

    def setUp(self):
        """测试前准备"""
        self.mock_chat_model = MagicMock()
        self.mock_retriever = MagicMock()

        self.chain = RAGChain(
            chat_model=self.mock_chat_model,
            retriever=self.mock_retriever,
            top_k=3,
        )

    def test_initialization(self):
        """测试初始化"""
        self.assertEqual(self.chain.top_k, 3)

    def test_invoke(self):
        """测试同步调用"""
        # 模拟检索结果
        self.mock_retriever.search_with_dict_output.return_value = [
            {
                "id": "img-1",
                "document": "A cat on a table",
                "metadata": {"file_path": "/path/to/cat.jpg"},
                "score": 0.9,
            }
        ]

        # 模拟模型响应
        mock_result = MagicMock()
        mock_result.content = "Based on the image, I can see a cat."
        self.mock_chat_model.invoke.return_value = mock_result

        # 调用 Chain（需要模拟文件读取）
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", MagicMock()):
                with patch("base64.b64encode", return_value=b"fake_base64"):
                    answer, documents = self.chain.invoke({"query": "What animal is in the image?"})

        # 验证结果
        self.assertEqual(len(documents), 1)

    async def test_ainvoke_with_image(self):
        """测试带图像的异步调用"""
        # 模拟检索结果
        mock_doc = Document(
            page_content="A sunset over the ocean",
            metadata={"id": "img-1", "file_path": "/path/to/sunset.jpg", "score": 0.95},
        )
        self.mock_retriever.image_to_image_search = AsyncMock(return_value=([mock_doc], "A beautiful sunset"))

        # 模拟模型响应
        mock_result = MagicMock()
        mock_result.content = "The image shows a beautiful sunset."
        self.mock_chat_model.ainvoke = AsyncMock(return_value=mock_result)

        # 创建模拟 UploadFile
        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b"fake_image_data")

        # 调用 Chain
        answer, documents = await self.chain.ainvoke_with_image("Describe the image", mock_file, top_k=1)

        # 验证结果
        self.assertEqual(answer, "The image shows a beautiful sunset.")
        self.assertEqual(len(documents), 1)

    def test_ainvoke_with_image_injects_history_and_context(self):
        """测试图片问答会注入历史、检索文档和文本片段"""
        mock_doc = Document(
            page_content="A sunset over the ocean",
            metadata={"id": "img-1", "file_path": "/path/to/sunset.jpg", "score": 0.95},
        )
        self.mock_retriever.image_to_image_search = AsyncMock(return_value=([mock_doc], "A beautiful sunset"))
        self.chain.doc_vector_store = MagicMock()
        self.chain.doc_vector_store.similarity_search.return_value = [{"content": "chunk-1"}]
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value="The image shows a beautiful sunset.")
        self.chain._chain = mock_chain

        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b"fake_image_data")

        answer, documents = asyncio.run(
            self.chain.ainvoke_with_image(
                "Describe the image",
                mock_file,
                top_k=1,
                chat_history=[("上一问", "上一答")],
            )
        )

        self.assertEqual(answer, "The image shows a beautiful sunset.")
        self.assertEqual(len(documents), 1)
        mock_chain.ainvoke.assert_awaited_once_with(
            {
                "query": "A beautiful sunset",
                "documents": [
                    {
                        "id": "img-1",
                        "document": "A sunset over the ocean",
                        "metadata": {"id": "img-1", "file_path": "/path/to/sunset.jpg", "score": 0.95},
                        "score": 0.95,
                    }
                ],
                "text_chunks": [{"content": "chunk-1"}],
                "chat_history": [("上一问", "上一答")],
            }
        )


class TestLangChainAdapter(unittest.TestCase):
    """测试 LangChain 适配器"""

    def setUp(self):
        """测试前准备"""
        self.mock_chain = MagicMock()
        self.mock_rag_chain = MagicMock()

        with patch("app.langchain_integration.adapters.get_image_description_chain", return_value=self.mock_chain):
            with patch("app.langchain_integration.adapters.get_rag_chain", return_value=self.mock_rag_chain):
                self.adapter = LangChainAdapter()

    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.adapter.image_description_chain)
        self.assertIsNotNone(self.adapter.rag_chain)

    async def test_text_to_image_search(self):
        """测试文本到图像检索适配"""
        # 模拟检索器
        mock_doc = Document(
            page_content="A cat sitting",
            metadata={"id": "img-1", "score": 0.9},
        )
        self.adapter.retriever.text_to_image_search = AsyncMock(return_value=[mock_doc])

        # 调用适配方法
        results = await self.adapter.text_to_image_search("cat", top_k=1)

        # 验证结果
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "img-1")
        self.adapter.retriever.text_to_image_search.assert_awaited_once_with("cat", top_k=1, fast=False)

    async def test_image_to_image_search(self):
        """测试图像到图像检索适配"""
        # 模拟检索器
        mock_doc = Document(
            page_content="A dog playing",
            metadata={"id": "img-2", "score": 0.85},
        )
        self.adapter.retriever.image_to_image_search = AsyncMock(return_value=([mock_doc], "A dog"))

        # 创建模拟 UploadFile
        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b"fake_image_data")

        # 调用适配方法
        results, description = await self.adapter.image_to_image_search(mock_file, top_k=1)

        # 验证结果
        self.assertEqual(description, "A dog")
        self.assertEqual(len(results), 1)
        self.adapter.retriever.image_to_image_search.assert_awaited_once_with(mock_file, top_k=1, fast=False)

    def test_answer_with_retrieved_images_respects_context_budget_without_text_augment(self):
        """测试图文回答在禁用文本补充时会裁剪图片和历史，并跳过文本检索"""
        self.adapter = LangChainAdapter(image_description_chain=MagicMock(), rag_chain=MagicMock())
        self.adapter.rag_chain.agenerate_from_context = AsyncMock(return_value="Budgeted answer")
        self.adapter.document_vector_store = MagicMock()

        documents = [{"id": "img-1"}, {"id": "img-2"}, {"id": "img-3"}]
        history = [("q1", "a1"), ("q2", "a2"), ("q3", "a3")]

        with patch("app.langchain_integration.adapters.settings.IMAGE_GROUNDED_TEXT_AUGMENT_ENABLED", False):
            with patch("app.langchain_integration.adapters.settings.IMAGE_GROUNDED_MAX_IMAGES", 2):
                with patch("app.langchain_integration.adapters.settings.IMAGE_GROUNDED_MAX_HISTORY_TURNS", 1):
                    answer = asyncio.run(
                        self.adapter._answer_with_retrieved_images(
                            query="帮我解释图片内容",
                            documents=documents,
                            chat_history=history,
                        )
                    )

        self.assertEqual(answer, "Budgeted answer")
        self.adapter.document_vector_store.similarity_search.assert_not_called()
        self.adapter.rag_chain.agenerate_from_context.assert_awaited_once_with(
            query="帮我解释图片内容",
            documents=[{"id": "img-1"}, {"id": "img-2"}],
            text_chunks=[],
            chat_history=[("q3", "a3")],
        )

    def test_answer_with_retrieved_images_uses_configured_text_augment_k(self):
        """测试图文回答在启用文本补充时按配置数量检索文本片段"""
        self.adapter = LangChainAdapter(image_description_chain=MagicMock(), rag_chain=MagicMock())
        self.adapter.rag_chain.agenerate_from_context = AsyncMock(return_value="Augmented answer")
        self.adapter.document_vector_store = MagicMock()
        self.adapter.document_vector_store.similarity_search.return_value = [{"content": "chunk-1"}]

        with patch("app.langchain_integration.adapters.settings.IMAGE_GROUNDED_TEXT_AUGMENT_ENABLED", True):
            with patch("app.langchain_integration.adapters.settings.IMAGE_GROUNDED_TEXT_TOP_K", 2):
                with patch("app.langchain_integration.adapters.settings.IMAGE_GROUNDED_MAX_IMAGES", 1):
                    with patch("app.langchain_integration.adapters.settings.IMAGE_GROUNDED_MAX_HISTORY_TURNS", 2):
                        answer = asyncio.run(
                            self.adapter._answer_with_retrieved_images(
                                query="帮我解释图片内容",
                                documents=[{"id": "img-1"}, {"id": "img-2"}],
                                chat_history=[("q1", "a1"), ("q2", "a2"), ("q3", "a3")],
                            )
                        )

        self.assertEqual(answer, "Augmented answer")
        self.adapter.document_vector_store.similarity_search.assert_called_once_with("帮我解释图片内容", k=2)
        self.adapter.rag_chain.agenerate_from_context.assert_awaited_once_with(
            query="帮我解释图片内容",
            documents=[{"id": "img-1"}],
            text_chunks=[{"content": "chunk-1"}],
            chat_history=[("q2", "a2"), ("q3", "a3")],
        )

    async def test_rag_chat_text(self):
        """测试文本 RAG 问答"""
        # 模拟 RAG Chain
        self.adapter.rag_chain.ainvoke = AsyncMock(return_value=("Answer text", [{"id": "img-1"}]))

        # 调用适配方法
        answer, documents, intent = await self.adapter.rag_chat("What is this?", top_k=1)

        # 验证结果
        self.assertEqual(answer, "Answer text")
        self.assertEqual(len(documents), 1)
        self.assertEqual(intent["execution_mode"], "multimodal_rag")

    async def test_rag_chat_with_image(self):
        """测试带图像的 RAG 问答"""
        # 模拟 RAG Chain
        self.adapter.rag_chain.ainvoke_with_image = AsyncMock(return_value=("Image answer", [{"id": "img-2"}]))

        # 创建模拟 UploadFile
        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b"fake_image_data")

        # 调用适配方法
        answer, documents, intent = await self.adapter.rag_chat("What is this?", top_k=1, image=mock_file)

        # 验证结果
        self.assertEqual(answer, "Image answer")
        self.assertEqual(len(documents), 1)
        self.assertEqual(intent["execution_mode"], "multimodal_rag")

    def test_rag_chat_with_image_uses_multimodal_rag_when_agentic_intent_requires_grounding(self):
        """测试启用 Agentic RAG 时带图知识问答仍统一走 multimodal_rag"""
        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b"fake_image_data")
        self.adapter.rag_chain.ainvoke_with_image = AsyncMock(return_value=("Image answer", [{"id": "img-2"}]))

        with patch("app.core.config.settings.AGENTIC_RAG_ENABLED", True):
            with patch(
                "app.langchain_integration.adapters.classify_chat_intent",
                AsyncMock(
                    return_value={
                        "presentation_mode": "rag_answer",
                        "execution_mode": "multimodal_rag",
                        "use_rag": True,
                        "has_uploaded_image": True,
                        "wants_images": True,
                        "confidence": 0.9,
                        "reason": "grounded_with_uploaded_image",
                    }
                ),
            ):
                answer, documents, intent = asyncio.run(
                    self.adapter.rag_chat(
                        "What is this?",
                        top_k=1,
                        image=mock_file,
                        chat_history=[("上一问", "上一答")],
                    )
                )

        self.assertEqual(answer, "Image answer")
        self.assertEqual(documents, [{"id": "img-2"}])
        self.assertEqual(intent["execution_mode"], "multimodal_rag")
        self.adapter.rag_chain.ainvoke_with_image.assert_awaited_once()

    def test_rag_chat_stream_text_uses_agentic_core_when_enabled(self):
        """测试启用 Agentic RAG 时文本流式也复用 Agentic 核心路径"""
        async def ordinary_stream(_inputs):
            yield "ordinary", [{"id": "img-ordinary"}]

        self.adapter.rag_chain.astream = ordinary_stream
        self.adapter.rag_chain.ainvoke = AsyncMock(return_value=("Agentic", [{"id": "img-1"}]))

        async def collect():
            items = []
            async for chunk, docs in self.adapter.rag_chat_stream(
                query="What is this?",
                top_k=1,
                chat_history=[("上一问", "上一答")],
            ):
                items.append((chunk, docs))
            return items

        with patch("app.core.config.settings.AGENTIC_RAG_ENABLED", True):
            with patch(
                "app.langchain_integration.adapters.classify_chat_intent",
                AsyncMock(
                    return_value={
                        "presentation_mode": "rag_answer",
                        "execution_mode": "multimodal_rag",
                        "use_rag": True,
                        "has_uploaded_image": False,
                        "wants_images": False,
                        "confidence": 0.92,
                        "reason": "internal_knowledge",
                    }
                ),
            ):
                streamed = asyncio.run(collect())

        self.assertEqual("".join(chunk for chunk, _ in streamed), "Agentic")
        self.assertTrue(all(docs == [{"id": "img-1"}] for _, docs in streamed))
        self.adapter.rag_chain.ainvoke.assert_awaited_once()


class TestRemediationRegressions(unittest.TestCase):
    """整改回归测试"""

    def test_generate_answer_uses_flat_message_list_and_chat_generation_content(self):
        """测试 Agentic RAG 生成使用单层消息列表并读取 message.content"""
        mock_model = MagicMock()
        mock_model._agenerate = AsyncMock(
            return_value=MagicMock(
                generations=[MagicMock(message=MagicMock(content="Generated answer"))]
            )
        )
        state = {
            "query": "问题",
            "chat_history": [("前一个问题", "前一个回答")],
            "documents": [{"document": "文档内容"}],
            "answer": "",
            "route": "",
            "relevance_score": 0.0,
            "needs_retry": False,
        }

        with patch("app.langchain_integration.agentic_rag.get_chat_model", return_value=mock_model):
            new_state = asyncio.run(generate_answer(state))

        self.assertEqual(new_state["answer"], "Generated answer")
        args = mock_model._agenerate.await_args.args[0]
        self.assertEqual(len(args), 1)
        self.assertIsInstance(args[0], HumanMessage)

    def test_compress_context_uses_flat_message_list_and_rewrites_document(self):
        """测试上下文压缩使用单层消息列表并返回压缩后的文本"""
        mock_model = MagicMock()
        mock_model._agenerate = AsyncMock(
            return_value=MagicMock(
                generations=[MagicMock(message=MagicMock(content="提取后的相关信息"))]
            )
        )
        documents = [{"id": "doc-1", "document": "a" * 80}]

        with patch("app.langchain_integration.context_compression.settings.CONTEXT_COMPRESSION_ENABLED", True):
            compressed = asyncio.run(compress_context("查询", documents, chat_model=mock_model))

        self.assertEqual(compressed[0]["document"], "提取后的相关信息")
        args = mock_model._agenerate.await_args.args[0]
        self.assertEqual(len(args), 1)
        self.assertIsInstance(args[0], HumanMessage)

    def test_cross_encoder_rerank_falls_back_to_config_for_non_positive_top_k(self):
        """测试 top_k 非正数时回退到配置值"""
        results = [
            {"id": "a", "document": "doc a"},
            {"id": "b", "document": "doc b"},
            {"id": "c", "document": "doc c"},
        ]

        with patch("app.retrieval.rerank.settings.RERANK_TOP_K", 2):
            with patch("app.retrieval.rerank._get_reranker", return_value=None):
                reranked = cross_encoder_rerank("query", results, top_k=0)

        self.assertEqual(len(reranked), 2)

    def test_classify_chat_intent_routes_common_fact_to_direct_llm(self):
        """测试通识问题直接走直答"""
        intent = asyncio.run(classify_chat_intent("长城在中国哪个城市附近？", has_uploaded_image=False))

        self.assertEqual(intent["presentation_mode"], "direct_answer")
        self.assertEqual(intent["execution_mode"], "direct_llm")
        self.assertFalse(intent["use_rag"])

    def test_classify_chat_intent_routes_internal_process_to_multimodal_rag(self):
        """测试内部流程问题统一走 multimodal_rag"""
        intent = asyncio.run(classify_chat_intent("公司的工资发放流程是什么？", has_uploaded_image=False))

        self.assertEqual(intent["presentation_mode"], "rag_answer")
        self.assertEqual(intent["execution_mode"], "multimodal_rag")
        self.assertTrue(intent["use_rag"])

    def test_classify_chat_intent_routes_image_lookup_to_similarity(self):
        """测试纯找图问题走图片检索"""
        intent = asyncio.run(classify_chat_intent("帮我找一张关于被通知裁员黄金一小时的图片", has_uploaded_image=False))

        self.assertEqual(intent["presentation_mode"], "image_only")
        self.assertEqual(intent["execution_mode"], "image_similarity")
        self.assertFalse(intent["use_rag"])

    def test_classify_chat_intent_keeps_find_image_request_as_image_only_even_if_query_contains_what(self):
        """测试“找图”请求即使包含“什么”也不应升级为图文回答"""
        intent = asyncio.run(
            classify_chat_intent("帮我找一张关于被通知裁员黄金一小时应该做什么的图片", has_uploaded_image=False)
        )

        self.assertEqual(intent["presentation_mode"], "image_only")
        self.assertEqual(intent["execution_mode"], "image_similarity")
        self.assertFalse(intent["use_rag"])

    def test_classify_chat_intent_routes_uploaded_image_question_to_uploaded_image_qa(self):
        """测试带图但只问上传图内容时走 uploaded_image_qa"""
        intent = asyncio.run(classify_chat_intent("这张图片里第2步应该做什么？", has_uploaded_image=True))

        self.assertEqual(intent["presentation_mode"], "direct_answer")
        self.assertEqual(intent["execution_mode"], "uploaded_image_qa")
        self.assertFalse(intent["use_rag"])

    def test_rag_chat_text_uses_direct_llm_when_agentic_intent_says_no_rag(self):
        """测试 Agentic 意图命中 direct_llm 时不走 RAG"""
        self.adapter = LangChainAdapter(image_description_chain=MagicMock(), rag_chain=MagicMock())
        self.adapter._answer_directly = AsyncMock(return_value="Direct answer")
        self.adapter.rag_chain.ainvoke = AsyncMock(return_value=("RAG answer", [{"id": "img-1"}]))

        with patch("app.core.config.settings.AGENTIC_RAG_ENABLED", True):
            with patch(
                "app.langchain_integration.adapters.classify_chat_intent",
                AsyncMock(
                    return_value={
                        "presentation_mode": "direct_answer",
                        "execution_mode": "direct_llm",
                        "use_rag": False,
                        "has_uploaded_image": False,
                        "wants_images": False,
                        "confidence": 0.95,
                        "reason": "common_fact",
                    }
                ),
            ):
                answer, documents, intent = asyncio.run(self.adapter.rag_chat("长城在中国哪个城市附近？", top_k=1))

        self.assertEqual(answer, "Direct answer")
        self.assertEqual(documents, [])
        self.assertEqual(intent["execution_mode"], "direct_llm")
        self.adapter._answer_directly.assert_awaited_once()
        self.adapter.rag_chain.ainvoke.assert_not_called()

    def test_rag_chat_text_uses_multimodal_rag_for_grounded_questions(self):
        """测试知识库问题统一走 multimodal_rag"""
        self.adapter = LangChainAdapter(image_description_chain=MagicMock(), rag_chain=MagicMock())
        self.adapter.rag_chain.ainvoke = AsyncMock(return_value=("Grounded answer", [{"id": "img-2"}]))

        with patch("app.core.config.settings.AGENTIC_RAG_ENABLED", True):
            with patch(
                "app.langchain_integration.adapters.classify_chat_intent",
                AsyncMock(
                    return_value={
                        "presentation_mode": "rag_answer",
                        "execution_mode": "multimodal_rag",
                        "use_rag": True,
                        "has_uploaded_image": False,
                        "wants_images": False,
                        "confidence": 0.91,
                        "reason": "internal_knowledge",
                    }
                ),
            ):
                answer, documents, intent = asyncio.run(self.adapter.rag_chat("公司的工资发放流程是什么？", top_k=1))

        self.assertEqual(answer, "Grounded answer")
        self.assertEqual(documents, [{"id": "img-2"}])
        self.assertEqual(intent["execution_mode"], "multimodal_rag")
        self.adapter.rag_chain.ainvoke.assert_awaited_once()

    def test_rag_chat_uses_image_similarity_for_image_only_requests(self):
        """测试纯找图请求走 image_similarity"""
        self.adapter = LangChainAdapter(image_description_chain=MagicMock(), rag_chain=MagicMock())
        self.adapter.text_to_image_search = AsyncMock(return_value=[{"id": "img-3"}])

        with patch("app.core.config.settings.AGENTIC_RAG_ENABLED", True):
            with patch(
                "app.langchain_integration.adapters.classify_chat_intent",
                AsyncMock(
                    return_value={
                        "presentation_mode": "image_only",
                        "execution_mode": "image_similarity",
                        "use_rag": False,
                        "has_uploaded_image": False,
                        "wants_images": True,
                        "confidence": 0.88,
                        "reason": "image_lookup",
                    }
                ),
            ):
                answer, documents, intent = asyncio.run(self.adapter.rag_chat("帮我找一张相关图片", top_k=1))

        self.assertIn("找到", answer)
        self.assertEqual(documents, [{"id": "img-3"}])
        self.assertEqual(intent["execution_mode"], "image_similarity")
        self.adapter.text_to_image_search.assert_awaited_once_with("帮我找一张相关图片", top_k=1, fast=True)

    def test_rag_chat_uses_fast_image_retrieval_for_image_grounded_answer(self):
        """测试图文回答图片检索走快路径，减少端到端耗时"""
        self.adapter = LangChainAdapter(image_description_chain=MagicMock(), rag_chain=MagicMock())
        self.adapter.text_to_image_search = AsyncMock(return_value=[{"id": "img-4"}])
        self.adapter._answer_with_retrieved_images = AsyncMock(return_value="Grounded image answer")

        with patch("app.core.config.settings.AGENTIC_RAG_ENABLED", True):
            with patch(
                "app.langchain_integration.adapters.classify_chat_intent",
                AsyncMock(
                    return_value={
                        "presentation_mode": "image_plus_answer",
                        "execution_mode": "image_grounded_answer",
                        "use_rag": True,
                        "has_uploaded_image": False,
                        "wants_images": True,
                        "confidence": 0.9,
                        "reason": "image_plus_answer",
                    }
                ),
            ):
                answer, documents, intent = asyncio.run(
                    self.adapter.rag_chat("帮我找图并解释图片内容", top_k=2)
                )

        self.assertEqual(answer, "Grounded image answer")
        self.assertEqual(documents, [{"id": "img-4"}])
        self.assertEqual(intent["execution_mode"], "image_grounded_answer")
        self.adapter.text_to_image_search.assert_awaited_once_with(
            "帮我找图并解释图片内容", top_k=2, fast=True
        )

    def test_rag_chat_uses_uploaded_image_qa_for_uploaded_image_question(self):
        """测试带图但只问上传图内容时走 uploaded_image_qa"""
        self.adapter = LangChainAdapter(image_description_chain=MagicMock(), rag_chain=MagicMock())
        self.adapter._answer_with_uploaded_image = AsyncMock(return_value="Uploaded image answer")
        mock_file = MagicMock()

        with patch("app.core.config.settings.AGENTIC_RAG_ENABLED", True):
            with patch(
                "app.langchain_integration.adapters.classify_chat_intent",
                AsyncMock(
                    return_value={
                        "presentation_mode": "direct_answer",
                        "execution_mode": "uploaded_image_qa",
                        "use_rag": False,
                        "has_uploaded_image": True,
                        "wants_images": False,
                        "confidence": 0.9,
                        "reason": "uploaded_image_only",
                    }
                ),
            ):
                answer, documents, intent = asyncio.run(
                    self.adapter.rag_chat("这张图片里第2步应该做什么？", top_k=1, image=mock_file)
                )

        self.assertEqual(answer, "Uploaded image answer")
        self.assertEqual(documents, [])
        self.assertEqual(intent["execution_mode"], "uploaded_image_qa")
        self.adapter._answer_with_uploaded_image.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
