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
from app.langchain_integration.doc_parser import (
    ParsedPdfTextChunk,
    ParsedPdfVisualAsset,
    build_pdf_text_chunks,
    extract_pdf_text_documents,
    extract_pdf_visual_assets,
)
from app.langchain_integration.vectorstores import ChromaVectorStore
from app.langchain_integration.retrievers import MultimodalRetriever
from app.langchain_integration.adapters import LangChainAdapter
from app.langchain_integration.agentic_rag import classify_chat_intent, generate_answer
from app.langchain_integration.context_compression import compress_context
from app.langchain_integration.models import (
    MultimodalChatModel,
    OpenAIEmbeddingsWrapper,
    _build_httpx_client_kwargs,
)
from app.core.config import _disable_process_proxy_env
from app.retrieval.rerank import cross_encoder_rerank
from app.retrieval.hybrid import rebuild_bm25_index
from app.application.schemas import DocumentRecordOut, ImageRecordOut
from app.application.schemas import SearchResultItem
from app.data.storage import BASE_STORAGE_DIR, DOC_STORAGE_DIR, STORAGE_ROOT


def _build_isolated_adapter() -> LangChainAdapter:
    """构造不依赖本地向量库环境的适配器测试实例。"""
    adapter = LangChainAdapter.__new__(LangChainAdapter)
    adapter.image_description_chain = MagicMock()
    adapter.rag_chain = MagicMock()
    adapter.vector_store = MagicMock()
    adapter.retriever = MagicMock()
    adapter.document_vector_store = MagicMock()
    adapter._bm25_add_chunks = MagicMock()
    adapter._bm25_add_document = MagicMock()
    adapter._rebuild_bm25_index = MagicMock()
    return adapter


class TestProxyBypassConfiguration(unittest.TestCase):
    """测试禁用环境代理继承的基础配置。"""

    def test_build_httpx_client_kwargs_disables_env_proxy(self):
        """统一 HTTP 客户端参数必须显式禁用环境代理继承。"""
        kwargs = _build_httpx_client_kwargs("https://example.com", 60)

        self.assertEqual(kwargs["base_url"], "https://example.com")
        self.assertEqual(kwargs["timeout"], 60)
        self.assertFalse(kwargs["trust_env"])

    @patch.dict(
        os.environ,
        {
            "HTTP_PROXY": "http://127.0.0.1:7890",
            "HTTPS_PROXY": "http://127.0.0.1:7890",
            "ALL_PROXY": "socks5://127.0.0.1:7890",
        },
        clear=False,
    )
    def test_disable_process_proxy_env_clears_proxy_variables(self):
        """后端进程启动时应清空代理环境变量并固定 NO_PROXY。"""
        _disable_process_proxy_env()

        self.assertNotIn("HTTP_PROXY", os.environ)
        self.assertNotIn("HTTPS_PROXY", os.environ)
        self.assertNotIn("ALL_PROXY", os.environ)
        self.assertEqual(os.environ["NO_PROXY"], "*")
        self.assertEqual(os.environ["no_proxy"], "*")


class TestModelClientsDisableEnvProxy(unittest.IsolatedAsyncioTestCase):
    """测试模型 HTTP 客户端不会继承系统代理。"""

    @patch("httpx.Client")
    def test_chat_model_generate_uses_trust_env_false(self, mock_client_cls):
        """同步聊天请求必须显式传 trust_env=False。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response

        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_client
        mock_cm.__exit__.return_value = False
        mock_client_cls.return_value = mock_cm

        model = MultimodalChatModel(
            base_url="https://example.com",
            api_key="test-key",
            model_name="test-model",
        )
        result = model._generate([HumanMessage(content="hello")])

        self.assertEqual(result.generations[0].message.content, "ok")
        self.assertFalse(mock_client_cls.call_args.kwargs["trust_env"])

    @patch("httpx.AsyncClient")
    async def test_embedding_wrapper_async_uses_trust_env_false(self, mock_async_client_cls):
        """异步 embedding 请求必须显式传 trust_env=False。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}],
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_client
        mock_cm.__aexit__.return_value = False
        mock_async_client_cls.return_value = mock_cm

        wrapper = OpenAIEmbeddingsWrapper(
            base_url="https://example.com",
            api_key="test-key",
            model_name="test-embedding",
        )
        embeddings = await wrapper.aembed_documents(["hello"])

        self.assertEqual(embeddings, [[0.1, 0.2, 0.3]])
        self.assertFalse(mock_async_client_cls.call_args.kwargs["trust_env"])


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


class TestChromaMetadataNormalization(unittest.TestCase):
    """测试 Chroma metadata 归一化。"""

    def test_add_texts_normalizes_empty_and_list_metadata_for_chroma(self):
        """测试向量存储会归一化空列表和列表元数据，避免 Chroma upsert 报错。"""
        vector_store = ChromaVectorStore.__new__(ChromaVectorStore)
        vector_store._vectorstore = MagicMock()

        vector_store.add_texts(
            ["table doc"],
            metadatas=[{"id": "img-1", "tags": [], "related_table_indices": [0, 1]}],
            ids=["img-1"],
        )

        kwargs = vector_store._vectorstore.add_texts.call_args.kwargs
        self.assertEqual(kwargs["metadatas"][0]["related_table_indices"], "[\"0\", \"1\"]")
        self.assertNotIn("tags", kwargs["metadatas"][0])

    def test_upsert_image_description_normalizes_tag_list_metadata(self):
        """测试图像描述 upsert 会把 tag 列表归一化为 Chroma 可接受的标量。"""
        vector_store = ChromaVectorStore.__new__(ChromaVectorStore)
        vector_store._vectorstore = MagicMock()

        vector_store.upsert_image_description(
            "image-123",
            "A beautiful sunset",
            {"file_path": "/path/to/sunset.jpg", "tags": ["hr", "policy"]},
        )

        kwargs = vector_store._vectorstore.add_texts.call_args.kwargs
        self.assertEqual(kwargs["metadatas"][0]["tags"], "hr,policy")


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
            with patch(
                "app.langchain_integration.retrievers.filter_enabled_image_hit_dicts",
                return_value=[mock_hit],
            ):
                with patch(
                    "app.langchain_integration.retrievers.filter_enabled_image_documents",
                    side_effect=lambda docs: docs,
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
                    with patch(
                        "app.langchain_integration.retrievers.filter_enabled_image_hit_dicts",
                        return_value=[mock_hit],
                    ):
                        with patch(
                            "app.langchain_integration.retrievers.filter_enabled_image_documents",
                            side_effect=lambda docs: docs,
                        ):
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
                    with patch(
                        "app.langchain_integration.retrievers.filter_enabled_image_hit_dicts",
                        return_value=[mock_hit],
                    ):
                        with patch(
                            "app.langchain_integration.retrievers.filter_enabled_image_documents",
                            side_effect=lambda docs: docs,
                        ):
                            results = asyncio.run(self.retriever.text_to_image_search("cat", top_k=2, fast=True))

        self.assertEqual(len(results), 1)
        mock_search.assert_awaited_once_with(
            "cat",
            self.mock_vector_store,
            20,
            enable_query_rewrite=True,
        )

    def test_text_to_image_search_filters_disabled_hits_before_rerank(self):
        """测试图片检索会在精排前过滤已禁用结果。"""
        active_hit = {
            "id": "img-active",
            "document": "Active result",
            "metadata": {"id": "img-active"},
            "rerank_score": 0.9,
        }
        disabled_hit = {
            "id": "img-disabled",
            "document": "Disabled result",
            "metadata": {"id": "img-disabled"},
            "rerank_score": 0.8,
        }

        with patch(
            "app.langchain_integration.retrievers._multi_query_hybrid_search",
            AsyncMock(return_value=[active_hit, disabled_hit]),
        ):
            with patch(
                "app.langchain_integration.retrievers.filter_enabled_image_hit_dicts",
                return_value=[active_hit],
            ) as mock_filter:
                with patch(
                    "app.langchain_integration.retrievers.filter_enabled_image_documents",
                    side_effect=lambda docs: docs,
                ) as mock_filter_docs:
                    with patch(
                    "app.langchain_integration.retrievers.cross_encoder_rerank",
                    return_value=[active_hit],
                    ) as mock_rerank:
                        results = asyncio.run(self.retriever.text_to_image_search("cat", top_k=2))

        self.assertEqual(len(results), 1)
        mock_filter.assert_called_once()
        mock_filter_docs.assert_called_once()
        mock_rerank.assert_called_once_with("cat", [active_hit], top_k=2)

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


class TestPdfParsing(unittest.TestCase):
    """测试 PDF 双通道解析"""

    def test_extract_pdf_text_documents_uses_loader_and_normalizes_page_metadata(self):
        """测试文本 loader 输出会规范化 page_number/file_name/source_type"""
        mock_loader_docs = [
            Document(page_content="第一页内容", metadata={"page": 0, "source": "temp.pdf"}),
            Document(page_content="第二页内容", metadata={"page": 1}),
        ]

        with patch("app.langchain_integration.doc_parser._get_pdf_text_loader_cls") as mock_loader_factory:
            mock_loader = MagicMock()
            mock_loader.load.return_value = mock_loader_docs
            mock_loader_cls = MagicMock(return_value=mock_loader)
            mock_loader_factory.return_value = mock_loader_cls

            documents = extract_pdf_text_documents("temp.pdf", file_name="example.pdf")

        self.assertEqual(len(documents), 2)
        mock_loader_cls.assert_called_once_with("temp.pdf")
        self.assertEqual(documents[0].metadata["page_number"], 1)
        self.assertEqual(documents[0].metadata["file_name"], "example.pdf")
        self.assertEqual(documents[0].metadata["source_type"], "pdf_page")
        self.assertEqual(documents[1].metadata["page_number"], 2)

    def test_build_pdf_text_chunks_preserves_page_number_and_continuous_chunk_index(self):
        """测试文本分块会保留页码并生成连续 chunk_index"""
        documents = [
            Document(page_content="第一句。第二句。", metadata={"page_number": 1, "file_name": "example.pdf"}),
            Document(page_content="第三句。", metadata={"page_number": 2, "file_name": "example.pdf"}),
        ]

        chunks = build_pdf_text_chunks(documents, doc_id="doc-1", chunk_size=4, chunk_overlap=0)

        self.assertGreaterEqual(len(chunks), 3)
        self.assertEqual([chunk.chunk_index for chunk in chunks], list(range(len(chunks))))
        self.assertEqual(chunks[0].page_number, 1)
        self.assertEqual(chunks[-1].page_number, 2)
        self.assertEqual(chunks[0].metadata["doc_id"], "doc-1")
        self.assertEqual(chunks[0].metadata["source_type"], "pdf_text_chunk")

    def test_parsed_pdf_visual_asset_exposes_page_and_asset_type(self):
        """测试视觉资产类型包含页码和资产类型"""
        asset = ParsedPdfVisualAsset(
            image_bytes=b"img",
            page_number=3,
            asset_type="table_page_render",
            metadata={"file_name": "example.pdf"},
        )

        self.assertEqual(asset.page_number, 3)
        self.assertEqual(asset.asset_type, "table_page_render")
        self.assertEqual(asset.metadata["file_name"], "example.pdf")

    def test_extract_pdf_visual_assets_prefers_table_crops_and_adds_page_fallback_when_context_matters(self):
        """测试含表格页默认生成表格裁图，并在上下文依赖时保留整页兜底图。"""
        fake_doc = MagicMock()
        fake_doc.extract_image.return_value = {"image": b""}

        page = MagicMock()
        page.rect = MagicMock(width=1000, height=1200)
        page.get_images.return_value = []
        page.get_text.return_value = [
            (80, 40, 920, 120, "工资发放流程说明", 0, 0, 0),
        ]
        crop_pixmap = MagicMock()
        crop_pixmap.tobytes.return_value = b"crop-bytes"
        full_pixmap = MagicMock()
        full_pixmap.tobytes.return_value = b"page-bytes"
        page.get_pixmap.side_effect = [crop_pixmap, full_pixmap]

        table = MagicMock()
        table.bbox = (100, 160, 900, 980)
        page.find_tables.return_value = MagicMock(tables=[table])
        fake_doc.__iter__.return_value = iter([page])

        with patch("app.langchain_integration.doc_parser.fitz.open", return_value=fake_doc):
            assets = extract_pdf_visual_assets(b"%PDF-test", file_name="policy.pdf")

        self.assertEqual([asset.asset_type for asset in assets], ["table_crop", "table_page_render"])
        self.assertEqual(assets[0].metadata["table_index_on_page"], 0)
        self.assertEqual(assets[0].metadata["table_count_on_page"], 1)
        self.assertEqual(assets[1].metadata["fallback_reason"], "important_nearby_text")

    def test_extract_pdf_visual_assets_groups_cross_page_tables_conservatively(self):
        """测试相邻页连续表格会被逻辑分组，并打上前后页连续标记。"""
        fake_doc = MagicMock()
        fake_doc.extract_image.return_value = {"image": b""}

        page_one = MagicMock()
        page_one.rect = MagicMock(width=1000, height=1200)
        page_one.get_images.return_value = []
        page_one.get_text.return_value = []
        page_one.find_tables.return_value = MagicMock(tables=[MagicMock(bbox=(100, 120, 900, 1160))])
        page_one_pix = MagicMock()
        page_one_pix.tobytes.return_value = b"page-one-crop"
        page_one.get_pixmap.return_value = page_one_pix

        page_two = MagicMock()
        page_two.rect = MagicMock(width=1000, height=1200)
        page_two.get_images.return_value = []
        page_two.get_text.return_value = []
        page_two.find_tables.return_value = MagicMock(tables=[MagicMock(bbox=(105, 40, 905, 1080))])
        page_two_pix = MagicMock()
        page_two_pix.tobytes.return_value = b"page-two-crop"
        page_two.get_pixmap.return_value = page_two_pix

        fake_doc.__iter__.return_value = iter([page_one, page_two])

        with patch("app.langchain_integration.doc_parser.fitz.open", return_value=fake_doc):
            assets = extract_pdf_visual_assets(b"%PDF-test", file_name="policy.pdf")

        self.assertEqual([asset.asset_type for asset in assets], ["table_crop", "table_crop"])
        group_ids = [asset.metadata.get("table_group_id") for asset in assets]
        self.assertEqual(group_ids[0], group_ids[1])
        self.assertTrue(assets[0].metadata["continued_to_next_page"])
        self.assertTrue(assets[1].metadata["continued_from_previous_page"])

    def test_extract_pdf_visual_assets_skips_tiny_decorative_embedded_images(self):
        """测试 PDF 会跳过明显的装饰性小图标，避免把无意义图案当作图片资产。"""
        fake_doc = MagicMock()
        fake_doc.extract_image.side_effect = [
            {"image": b"x" * 512, "width": 24, "height": 24},
            {"image": b"y" * 4096, "width": 320, "height": 200},
        ]

        page = MagicMock()
        page.rect = MagicMock(width=1000, height=1200)
        page.get_images.return_value = [(11,), (22,)]
        page.get_image_rects.side_effect = [
            [MagicMock(x0=20, y0=20, x1=44, y1=44)],
            [MagicMock(x0=120, y0=180, x1=620, y1=520)],
        ]
        page.get_text.return_value = []
        page.find_tables.return_value = MagicMock(tables=[])
        fake_doc.__iter__.return_value = iter([page])

        with patch("app.langchain_integration.doc_parser.fitz.open", return_value=fake_doc):
            assets = extract_pdf_visual_assets(b"%PDF-test", file_name="policy.pdf")

        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].asset_type, "embedded_image")
        self.assertEqual(assets[0].metadata["image_width"], 320)
        self.assertEqual(assets[0].metadata["image_height"], 200)

    def test_extract_pdf_visual_assets_adds_page_render_when_page_only_contains_fragmented_images(self):
        """测试页面只有大量碎片化图片时，会退化为整页渲染而不是收集一堆局部图案。"""
        fake_doc = MagicMock()
        fake_doc.extract_image.side_effect = [
            {"image": b"x" * 800, "width": 32, "height": 32}
            for _ in range(6)
        ]

        page = MagicMock()
        page.rect = MagicMock(width=1000, height=1200)
        page.get_images.return_value = [(11,), (12,), (13,), (14,), (15,), (16,)]
        page.get_image_rects.side_effect = [
            [MagicMock(x0=40, y0=120, x1=210, y1=290)],
            [MagicMock(x0=220, y0=120, x1=390, y1=290)],
            [MagicMock(x0=400, y0=120, x1=570, y1=290)],
            [MagicMock(x0=40, y0=310, x1=210, y1=480)],
            [MagicMock(x0=220, y0=310, x1=390, y1=480)],
            [MagicMock(x0=400, y0=310, x1=570, y1=480)],
        ]
        page.get_text.return_value = []
        page.find_tables.return_value = MagicMock(tables=[])
        page_pixmap = MagicMock()
        page_pixmap.tobytes.return_value = b"page-render"
        page.get_pixmap.return_value = page_pixmap
        fake_doc.__iter__.return_value = iter([page])

        with patch("app.langchain_integration.doc_parser.fitz.open", return_value=fake_doc):
            assets = extract_pdf_visual_assets(b"%PDF-test", file_name="poster.pdf")

        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].asset_type, "page_render")
        self.assertEqual(assets[0].metadata["fallback_reason"], "fragmented_or_filtered_images")


class TestStoragePaths(unittest.TestCase):
    """测试运行时存储路径共享同一个根目录。"""

    def test_storage_paths_share_single_root(self):
        self.assertEqual(BASE_STORAGE_DIR.parent, STORAGE_ROOT)
        self.assertEqual(DOC_STORAGE_DIR.parent, STORAGE_ROOT)
        self.assertTrue(str(STORAGE_ROOT).endswith("storage"))


class TestRAGChain(unittest.TestCase):
    """测试 RAG Chain"""

    def setUp(self):
        """测试前准备"""
        self.mock_chat_model = MagicMock()
        self.mock_retriever = MagicMock()

        self.chain = RAGChain(
            chat_model=self.mock_chat_model,
            retriever=self.mock_retriever,
            doc_vector_store=MagicMock(),
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
        self.mock_vector_store = MagicMock()
        self.mock_document_vector_store = MagicMock()
        self.mock_retriever = MagicMock()

        with patch("app.langchain_integration.adapters.get_image_description_chain", return_value=self.mock_chain):
            with patch("app.langchain_integration.adapters.get_rag_chain", return_value=self.mock_rag_chain):
                with patch("app.langchain_integration.adapters.get_vector_store", return_value=self.mock_vector_store):
                    with patch("app.langchain_integration.adapters.get_document_vector_store", return_value=self.mock_document_vector_store):
                        with patch("app.langchain_integration.adapters.get_multimodal_retriever", return_value=self.mock_retriever):
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
        self.adapter = _build_isolated_adapter()
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
        self.adapter = _build_isolated_adapter()
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

    def test_process_pdf_upload_uses_structured_pdf_outputs_and_page_metadata(self):
        """测试 PDF 上传会消费结构化解析结果并把页码 metadata 写入向量库"""
        self.adapter = _build_isolated_adapter()
        self.adapter.image_description_chain.ainvoke = AsyncMock(return_value="表格页描述")

        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b"%PDF-test")
        mock_file.filename = "policy.pdf"

        parsed_chunks = [
            ParsedPdfTextChunk(
                content="第一页第一段",
                page_number=1,
                chunk_index=0,
                metadata={
                    "doc_id": "doc-x",
                    "page_number": 1,
                    "file_name": "policy.pdf",
                    "source_type": "pdf_text_chunk",
                },
            )
        ]
        visual_assets = [
            ParsedPdfVisualAsset(
                image_bytes=b"png-bytes",
                page_number=2,
                asset_type="table_page_render",
                metadata={"page_number": 2, "file_name": "policy.pdf", "asset_type": "table_page_render"},
            )
        ]

        with patch("app.langchain_integration.adapters.uuid.uuid4", side_effect=["doc-x", "img-x"]):
            with patch("app.langchain_integration.adapters.extract_pdf_text_documents", return_value=[Document(page_content="第一页", metadata={"page_number": 1})]):
                with patch("app.langchain_integration.adapters.build_pdf_text_chunks", return_value=parsed_chunks):
                    with patch("app.langchain_integration.adapters.extract_pdf_visual_assets", return_value=visual_assets):
                        with patch("app.langchain_integration.adapters.get_doc_path", return_value="temp.pdf"):
                            with patch("builtins.open", unittest.mock.mock_open()):
                                asyncio.run(self.adapter.process_pdf_upload(mock_db, mock_file))

        self.adapter.document_vector_store.upsert_chunks.assert_called_once_with(
            doc_id="doc-x",
            chunks=["第一页第一段"],
            metadatas=[
                {
                    **parsed_chunks[0].metadata,
                    "enabled": False,
                    "document_type": "pdf",
                }
            ],
        )
        stored_doc = self.adapter.vector_store.add_documents.call_args[0][0][0]
        self.assertEqual(stored_doc.metadata["page_number"], 2)
        self.assertEqual(stored_doc.metadata["asset_type"], "table_page_render")

    def test_process_pdf_upload_preserves_table_crop_group_metadata(self):
        """测试 PDF 上传会把表格裁图与跨页分组 metadata 写入图片向量库与记录。"""
        self.adapter = _build_isolated_adapter()
        self.adapter.image_description_chain.ainvoke = AsyncMock(return_value="跨页表格描述")

        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b"%PDF-test")
        mock_file.filename = "policy.pdf"

        parsed_chunks = []
        visual_assets = [
            ParsedPdfVisualAsset(
                image_bytes=b"crop-one",
                page_number=2,
                asset_type="table_crop",
                metadata={
                    "page_number": 2,
                    "file_name": "policy.pdf",
                    "asset_type": "table_crop",
                    "table_index_on_page": 0,
                    "table_count_on_page": 1,
                    "table_group_id": "policy.pdf:table-group:1",
                    "continued_to_next_page": True,
                },
            )
        ]

        with patch("app.langchain_integration.adapters.uuid.uuid4", side_effect=["doc-x", "img-x"]):
            with patch("app.langchain_integration.adapters.extract_pdf_text_documents", return_value=[]):
                with patch("app.langchain_integration.adapters.build_pdf_text_chunks", return_value=parsed_chunks):
                    with patch("app.langchain_integration.adapters.extract_pdf_visual_assets", return_value=visual_assets):
                        with patch("app.langchain_integration.adapters.get_doc_path", return_value="temp.pdf"):
                            with patch("builtins.open", unittest.mock.mock_open()):
                                asyncio.run(self.adapter.process_pdf_upload(mock_db, mock_file))

        stored_doc = self.adapter.vector_store.add_documents.call_args[0][0][0]
        self.assertEqual(stored_doc.metadata["asset_type"], "table_crop")
        self.assertEqual(stored_doc.metadata["table_group_id"], "policy.pdf:table-group:1")
        self.assertTrue(stored_doc.metadata["continued_to_next_page"])

    def test_process_pdf_upload_retries_transient_chunk_upsert_failures(self):
        """测试 PDF 上传遇到瞬时 embedding/SSL 错误时会重试文本向量写入。"""
        self.adapter = _build_isolated_adapter()
        self.adapter.image_description_chain.ainvoke = AsyncMock(return_value="表格页描述")
        self.adapter.document_vector_store.upsert_chunks = MagicMock(
            side_effect=[Exception("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred"), None]
        )

        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b"%PDF-test")
        mock_file.filename = "policy.pdf"

        parsed_chunks = [
            ParsedPdfTextChunk(
                content="第一页第一段",
                page_number=1,
                chunk_index=0,
                metadata={
                    "doc_id": "doc-x",
                    "page_number": 1,
                    "file_name": "policy.pdf",
                    "source_type": "pdf_text_chunk",
                },
            )
        ]

        with patch("app.langchain_integration.adapters.uuid.uuid4", side_effect=["doc-x"]):
            with patch("app.langchain_integration.adapters.extract_pdf_text_documents", return_value=[]):
                with patch("app.langchain_integration.adapters.build_pdf_text_chunks", return_value=parsed_chunks):
                    with patch("app.langchain_integration.adapters.extract_pdf_visual_assets", return_value=[]):
                        with patch("app.langchain_integration.adapters.get_doc_path", return_value="temp.pdf"):
                            with patch("builtins.open", unittest.mock.mock_open()):
                                with patch("app.langchain_integration.adapters.time.sleep", return_value=None):
                                    record = asyncio.run(self.adapter.process_pdf_upload(mock_db, mock_file))

        self.assertEqual(self.adapter.document_vector_store.upsert_chunks.call_count, 2)
        self.assertEqual(record.status, "Completed")

    def test_text_to_image_search_prefers_table_crop_when_scores_match(self):
        """测试同等分数下 table_crop 优先于 table_page_render。"""
        retriever = MultimodalRetriever(vector_store=MagicMock(), chat_model=MagicMock(), top_k=2)
        crop_hit = {
            "id": "crop-1",
            "document": "工资表格裁图",
            "metadata": {"id": "crop-1", "asset_type": "table_crop"},
            "rerank_score": 0.9,
        }
        page_hit = {
            "id": "page-1",
            "document": "工资整页图",
            "metadata": {"id": "page-1", "asset_type": "table_page_render"},
            "rerank_score": 0.9,
        }

        with patch(
            "app.langchain_integration.retrievers._multi_query_hybrid_search",
            AsyncMock(return_value=[page_hit, crop_hit]),
        ):
            with patch(
                "app.langchain_integration.retrievers.filter_enabled_image_hit_dicts",
                return_value=[page_hit, crop_hit],
            ):
                with patch(
                    "app.langchain_integration.retrievers.cross_encoder_rerank",
                    return_value=[page_hit, crop_hit],
                ):
                    with patch(
                        "app.langchain_integration.retrievers.filter_enabled_image_documents",
                        side_effect=lambda docs: docs,
                    ):
                        results = asyncio.run(retriever.text_to_image_search("工资流程表", top_k=2))

        self.assertEqual([doc.metadata["id"] for doc in results], ["crop-1", "page-1"])

    def test_delete_image_record_cleans_vector_and_rebuilds_bm25(self):
        self.adapter = _build_isolated_adapter()
        record = MagicMock()
        record.id = "img-1"
        record.file_path = "storage/images/custom/img-1.jpg"
        mock_db = MagicMock()

        with patch("app.langchain_integration.adapters.safe_unlink", return_value=True) as mock_unlink:
            warnings = self.adapter.delete_image_record(mock_db, record)

        self.adapter.vector_store.delete.assert_called_once_with(ids=["img-1"])
        mock_db.delete.assert_called_once_with(record)
        mock_db.commit.assert_called_once()
        self.adapter._rebuild_bm25_index.assert_called_once()
        mock_unlink.assert_called_once_with(record.file_path)
        self.assertEqual(warnings, [])

    def test_delete_document_record_removes_related_images_and_chunks(self):
        self.adapter = _build_isolated_adapter()
        record = MagicMock()
        record.id = "doc-1"
        record.file_path = "storage/docs/doc-1.pdf"
        derived = MagicMock()
        derived.id = "img-2"
        derived.file_path = "storage/images/custom/img-2.jpg"
        mock_db = MagicMock()

        with patch("app.langchain_integration.adapters.get_document_image_records", return_value=[derived]):
            with patch("app.langchain_integration.adapters.safe_unlink", return_value=True):
                warnings = self.adapter.delete_document_record(mock_db, record)

        self.adapter.document_vector_store.delete_document.assert_called_once_with("doc-1")
        self.adapter.vector_store.delete.assert_called_once_with(ids=["img-2"])
        self.assertEqual(mock_db.delete.call_count, 2)
        self.adapter._rebuild_bm25_index.assert_called_once()
        self.assertEqual(warnings, [])

    def test_reprocess_image_record_updates_description_and_vector(self):
        self.adapter = _build_isolated_adapter()
        self.adapter.image_description_chain.ainvoke = AsyncMock(return_value="new description")
        record = MagicMock()
        record.id = "img-1"
        record.file_path = "storage/images/custom/img-1.jpg"
        record.source_dataset = "custom"
        record.title = "Image 1"
        record.tags = "tag1,tag2"
        record.enabled = True
        mock_db = MagicMock()

        with patch("app.langchain_integration.adapters.Path.exists", return_value=True):
            with patch("app.langchain_integration.adapters.Path.read_bytes", return_value=b"img-bytes"):
                warnings = asyncio.run(self.adapter.reprocess_image_record(mock_db, record))

        self.assertEqual(record.generated_description, "new description")
        self.adapter.vector_store.upsert_image_description.assert_called_once()
        self.adapter._rebuild_bm25_index.assert_called_once()
        self.assertEqual(warnings, [])

    def test_reprocess_document_record_marks_failed_when_ingest_raises(self):
        self.adapter = _build_isolated_adapter()
        self.adapter.delete_document_record = MagicMock(return_value=[])
        self.adapter._ingest_pdf_record = AsyncMock(side_effect=Exception("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred"))
        record = MagicMock()
        record.id = "doc-1"
        record.file_path = "storage/docs/doc-1.pdf"
        record.file_name = "policy.pdf"
        record.status = "Completed"
        record.chunk_count = 5
        record.image_count = 3
        mock_db = MagicMock()

        with patch("app.langchain_integration.adapters.Path.exists", return_value=True):
            with patch("app.langchain_integration.adapters.Path.read_bytes", return_value=b"%PDF-test"):
                with self.assertRaises(Exception):
                    asyncio.run(self.adapter.reprocess_document_record(mock_db, record))

        self.assertEqual(record.status, "Failed")
        self.assertIn("SSL", record.extra_metadata)
        self.adapter._rebuild_bm25_index.assert_not_called()

    def test_sync_document_record_vectors_updates_chunk_and_image_metadata(self):
        self.adapter = _build_isolated_adapter()
        self.adapter.document_vector_store.refresh_document_metadata = MagicMock()
        record = MagicMock()
        record.id = "doc-1"
        record.enabled = False
        record.document_type = "pdf"
        record.file_name = "policy.pdf"
        derived = MagicMock()
        derived.generated_description = "desc"
        derived.id = "img-1"
        derived.file_path = "storage/images/custom/img-1.jpg"
        derived.source_dataset = "pdf"
        derived.title = "Image"
        derived.tags = "a,b"
        derived.enabled = True
        derived.extra_metadata = '{"doc_id":"doc-1"}'
        mock_db = MagicMock()

        with patch("app.langchain_integration.adapters.get_document_image_records", return_value=[derived]):
            self.adapter.sync_document_record_vectors(mock_db, record)

        self.adapter.document_vector_store.refresh_document_metadata.assert_called_once_with(
            "doc-1",
            {"enabled": False, "document_type": "pdf", "file_name": "policy.pdf"},
        )
        self.adapter.vector_store.upsert_image_description.assert_called_once()

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
        self.adapter = _build_isolated_adapter()
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
        self.adapter = _build_isolated_adapter()
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
        self.adapter = _build_isolated_adapter()
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
        self.adapter = _build_isolated_adapter()
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
        self.adapter = _build_isolated_adapter()
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

    def test_image_record_out_splits_tags_and_custom_metadata(self):
        record = MagicMock()
        record.id = "img-1"
        record.file_path = "storage/images/custom/img-1.jpg"
        record.upload_time = "2025-01-01T00:00:00"
        record.generated_description = "desc"
        record.status = "Completed"
        record.source_dataset = "custom"
        record.title = "Title"
        record.tags = "hr,policy"
        record.notes = "note"
        record.enabled = True
        record.custom_metadata = '{"department":"HR"}'

        payload = ImageRecordOut.model_validate(record)
        self.assertEqual(payload.tags, ["hr", "policy"])
        self.assertEqual(payload.custom_metadata["department"], "HR")

    def test_image_record_out_exposes_table_asset_metadata(self):
        record = MagicMock()
        record.id = "img-table"
        record.file_path = "storage/images/custom/img-table.jpg"
        record.upload_time = "2025-01-01T00:00:00"
        record.generated_description = "table desc"
        record.status = "Completed"
        record.source_dataset = "pdf"
        record.title = "工资流程表"
        record.tags = ""
        record.notes = ""
        record.enabled = True
        record.custom_metadata = None
        record.extra_metadata = (
            '{"page_number":2,"asset_type":"table_crop","table_index_on_page":0,'
            '"table_group_id":"policy.pdf:table-group:1","continued_to_next_page":true}'
        )

        payload = ImageRecordOut.model_validate(record)
        self.assertEqual(payload.asset_type, "table_crop")
        self.assertEqual(payload.page_number, 2)
        self.assertEqual(payload.table_index_on_page, 0)
        self.assertEqual(payload.table_group_id, "policy.pdf:table-group:1")
        self.assertTrue(payload.continued_to_next_page)

    def test_search_result_item_exposes_table_asset_metadata(self):
        payload = SearchResultItem(
            id="img-table",
            file_path="storage/images/custom/img-table.jpg",
            description="table desc",
            score=0.12,
            asset_type="table_crop",
            page_number=3,
            table_group_id="policy.pdf:table-group:2",
            continued_from_previous_page=True,
            continued_to_next_page=False,
        )

        self.assertEqual(payload.asset_type, "table_crop")
        self.assertEqual(payload.page_number, 3)
        self.assertEqual(payload.table_group_id, "policy.pdf:table-group:2")
        self.assertTrue(payload.continued_from_previous_page)

    def test_document_record_out_splits_tags_and_custom_metadata(self):
        record = MagicMock()
        record.id = "doc-1"
        record.file_name = "policy.pdf"
        record.title = "Policy"
        record.file_path = "storage/docs/doc-1.pdf"
        record.upload_time = "2025-01-01T00:00:00"
        record.status = "Completed"
        record.chunk_count = 3
        record.image_count = 1
        record.document_type = "pdf"
        record.tags = "hr,policy"
        record.notes = "note"
        record.enabled = True
        record.custom_metadata = '{"department":"HR"}'

        payload = DocumentRecordOut.model_validate(record)
        self.assertEqual(payload.tags, ["hr", "policy"])
        self.assertEqual(payload.custom_metadata["department"], "HR")

    def test_document_vector_similarity_search_filters_disabled_documents(self):
        """测试文本 chunk 检索会过滤已禁用文档。"""
        store = MagicMock()
        doc_vs = store
        doc_vs._vectorstore = MagicMock()
        doc_vs._vectorstore.similarity_search_with_relevance_scores.return_value = [
            (
                Document(
                    page_content="chunk-1",
                    metadata={"doc_id": "doc-1", "chunk_index": 0},
                ),
                0.9,
            ),
            (
                Document(
                    page_content="chunk-2",
                    metadata={"doc_id": "doc-2", "chunk_index": 1},
                ),
                0.8,
            ),
        ]

        from app.langchain_integration.vectorstores import DocumentVectorStore

        instance = DocumentVectorStore.__new__(DocumentVectorStore)
        instance._vectorstore = doc_vs._vectorstore

        with patch(
            "app.langchain_integration.vectorstores.filter_enabled_text_chunk_hits",
            return_value=[{"doc_id": "doc-1", "chunk_index": 0, "content": "chunk-1", "metadata": {"doc_id": "doc-1"}, "score": 0.9}],
        ) as mock_filter:
            hits = instance.similarity_search("query", k=2)

        self.assertEqual(len(hits), 1)
        mock_filter.assert_called_once()

    def test_rebuild_bm25_index_only_includes_enabled_assets(self):
        """测试 BM25 全量重建只纳入启用的图片和文档。"""
        bm25_index = MagicMock()
        mock_session = MagicMock()
        enabled_image = MagicMock()
        enabled_image.id = "img-1"
        enabled_image.extra_metadata = None
        disabled_image = MagicMock()
        disabled_image.id = "img-2"
        disabled_image.extra_metadata = None
        enabled_doc = MagicMock()
        enabled_doc.id = "doc-1"

        image_query = MagicMock()
        image_query.filter.return_value.all.return_value = [enabled_image]
        doc_query = MagicMock()
        doc_query.filter.return_value.all.return_value = [enabled_doc]
        mock_session.query.side_effect = [image_query, doc_query]

        image_collection = MagicMock()
        image_collection.get.return_value = {
            "ids": ["img-1", "img-2"],
            "documents": ["enabled image", "disabled image"],
            "metadatas": [{}, {}],
        }
        doc_collection = MagicMock()
        doc_collection.get.return_value = {
            "ids": ["doc-1_chunk_0", "doc-2_chunk_0"],
            "documents": ["enabled chunk", "disabled chunk"],
            "metadatas": [{"doc_id": "doc-1"}, {"doc_id": "doc-2"}],
        }

        image_vs = MagicMock()
        image_vs.vectorstore._collection = image_collection
        doc_vs = MagicMock()
        doc_vs._vectorstore._collection = doc_collection

        session_factory = MagicMock()
        session_factory.return_value.__enter__.return_value = mock_session
        session_factory.return_value.__exit__.return_value = False

        with patch("app.data.database.SessionLocal", session_factory):
            with patch("app.langchain_integration.vectorstores.get_vector_store", return_value=image_vs):
                with patch("app.langchain_integration.vectorstores.get_document_vector_store", return_value=doc_vs):
                    rebuild_bm25_index(bm25_index)

        bm25_index.build.assert_called_once_with(
            ["img-1", "doc-1_chunk_0"],
            ["enabled image", "enabled chunk"],
        )


if __name__ == "__main__":
    unittest.main()
