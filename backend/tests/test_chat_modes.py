import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.langchain_integration.adapters import LangChainAdapter


async def _yield_chunks(*chunks):
    for chunk in chunks:
        yield chunk


def _build_mode_test_adapter() -> LangChainAdapter:
    adapter = LangChainAdapter.__new__(LangChainAdapter)
    adapter.image_description_chain = MagicMock()
    adapter.rag_chain = MagicMock()
    adapter.rag_chain.text_top_k = 5
    adapter.rag_chain.ainvoke = AsyncMock(return_value=("rag answer", [{"id": "doc-1", "document": "ctx", "metadata": {}, "score": 0.8}]))
    adapter.rag_chain.ainvoke_with_image = AsyncMock(return_value=("image rag", [{"id": "img-1", "document": "ctx", "metadata": {}, "score": 0.8}]))
    adapter.rag_chain.astream_from_context = MagicMock(side_effect=lambda **kwargs: _yield_chunks("A", "B"))
    adapter.vector_store = MagicMock()
    adapter.retriever = MagicMock()
    adapter.document_vector_store = MagicMock()
    adapter.document_vector_store.search_with_pipeline = MagicMock(return_value=[])
    adapter.document_vector_store.async_search_with_pipeline = AsyncMock(return_value=[])
    adapter._answer_directly = AsyncMock(return_value="direct answer")
    adapter._answer_with_uploaded_image = AsyncMock(return_value="uploaded image answer")
    adapter._save_uploaded_image_to_kb = AsyncMock(return_value=("saved", []))
    adapter._retrieve_images_for_query = AsyncMock(return_value=[{"id": "img-1", "document": "image", "metadata": {}, "score": 0.7}])
    adapter._answer_with_retrieved_images = AsyncMock(return_value="grounded answer")
    return adapter


class TestChatModes(unittest.IsolatedAsyncioTestCase):
    async def test_fast_mode_unmatched_text_falls_back_to_direct_llm_without_classifier(self):
        adapter = _build_mode_test_adapter()
        with patch("app.langchain_integration.adapters.classify_chat_intent", new=AsyncMock(side_effect=AssertionError("classifier should not be called"))):
            answer, documents, intent = await adapter.rag_chat(
                query="帮我总结一下这个主题的核心观点",
                top_k=2,
                chat_mode="fast",
            )

        self.assertEqual(answer, "direct answer")
        self.assertEqual(documents, [])
        self.assertEqual(intent["execution_mode"], "direct_llm")
        adapter._answer_directly.assert_awaited_once()

    async def test_fast_mode_with_uploaded_image_falls_back_to_uploaded_image_qa(self):
        adapter = _build_mode_test_adapter()
        mock_file = MagicMock()
        with patch("app.langchain_integration.adapters.classify_chat_intent", new=AsyncMock(side_effect=AssertionError("classifier should not be called"))):
            answer, documents, intent = await adapter.rag_chat(
                query="请帮我看看",
                top_k=2,
                image=mock_file,
                chat_mode="fast",
            )

        self.assertEqual(answer, "uploaded image answer")
        self.assertEqual(documents, [])
        self.assertEqual(intent["execution_mode"], "uploaded_image_qa")
        adapter._answer_with_uploaded_image.assert_awaited_once()

    async def test_expert_mode_always_calls_classifier_even_for_rule_match(self):
        adapter = _build_mode_test_adapter()
        classifier = AsyncMock(
            return_value={
                "presentation_mode": "direct_answer",
                "execution_mode": "direct_llm",
                "use_rag": False,
                "has_uploaded_image": False,
                "wants_images": False,
                "confidence": 0.9,
                "reason": "expert_stub",
            }
        )
        with patch("app.langchain_integration.adapters.classify_chat_intent", new=classifier):
            answer, documents, intent = await adapter.rag_chat(
                query="长城位于哪里？",
                top_k=2,
                chat_mode="expert",
            )

        self.assertEqual(answer, "direct answer")
        self.assertEqual(documents, [])
        self.assertEqual(intent["reason"], "expert_stub")
        classifier.assert_awaited_once()
        self.assertEqual(classifier.await_args.kwargs["mode"], "expert")

    async def test_expert_mode_forces_agentic_runner_for_multimodal_rag(self):
        adapter = _build_mode_test_adapter()
        classifier = AsyncMock(
            return_value={
                "presentation_mode": "rag_answer",
                "execution_mode": "multimodal_rag",
                "use_rag": True,
                "has_uploaded_image": False,
                "wants_images": False,
                "confidence": 0.92,
                "reason": "expert_rag",
            }
        )
        agentic_runner = AsyncMock(return_value=("expert rag answer", [{"id": "doc-9", "document": "ctx", "metadata": {}, "score": 0.9}], [{"key": "retrieve", "label": "检索"}]))

        with patch("app.langchain_integration.adapters.classify_chat_intent", new=classifier), \
             patch("app.langchain_integration.adapters.run_agentic_multimodal_rag", new=agentic_runner), \
             patch("app.langchain_integration.adapters.settings.CHAT_EXPERT_FORCE_AGENTIC_RAG", True):
            answer, documents, intent = await adapter.rag_chat(
                query="公司的工资发放流程是什么？",
                top_k=3,
                chat_mode="expert",
            )

        self.assertEqual(answer, "expert rag answer")
        self.assertEqual(documents[0]["id"], "doc-9")
        self.assertEqual(intent["retrieval_steps"][0]["key"], "retrieve")
        agentic_runner.assert_awaited_once()

    async def test_fast_mode_multimodal_rag_uses_fast_profile(self):
        adapter = _build_mode_test_adapter()
        adapter._run_scoped_chat = AsyncMock(
            return_value=(
                "scoped answer",
                [{"id": "doc-fast", "document": "ctx", "metadata": {}, "score": 0.7}],
                {"execution_mode": "multimodal_rag", "presentation_mode": "rag_answer", "use_rag": True, "reason": "ok"},
            )
        )

        answer, documents, _intent = await adapter.rag_chat(
            query="公司内部报销流程是什么？",
            top_k=2,
            chat_mode="fast",
        )

        self.assertEqual(answer, "scoped answer")
        self.assertEqual(documents[0]["id"], "doc-fast")
        scoped_kwargs = adapter._run_scoped_chat.await_args.kwargs
        self.assertEqual(scoped_kwargs["execution_hint"], "multimodal_rag")
        self.assertFalse(scoped_kwargs["retrieval_profile"]["enable_query_rewrite"])
        self.assertFalse(scoped_kwargs["retrieval_profile"]["enable_rerank"])
        self.assertFalse(scoped_kwargs["retrieval_profile"]["enable_context_compression"])

    async def test_expert_mode_agentic_runner_receives_expert_profile(self):
        adapter = _build_mode_test_adapter()
        classifier = AsyncMock(
            return_value={
                "presentation_mode": "rag_answer",
                "execution_mode": "multimodal_rag",
                "use_rag": True,
                "has_uploaded_image": False,
                "wants_images": False,
                "confidence": 0.92,
                "reason": "expert_rag",
            }
        )
        agentic_runner = AsyncMock(return_value=("expert rag answer", [{"id": "doc-9", "document": "ctx", "metadata": {}, "score": 0.9}], [{"key": "retrieve", "label": "检索"}]))

        with patch("app.langchain_integration.adapters.classify_chat_intent", new=classifier), \
             patch("app.langchain_integration.adapters.run_agentic_multimodal_rag", new=agentic_runner), \
             patch("app.langchain_integration.adapters.settings.CHAT_EXPERT_FORCE_AGENTIC_RAG", True), \
             patch("app.langchain_integration.adapters.settings.CHAT_EXPERT_RERANK_CANDIDATE_K", 40), \
             patch("app.langchain_integration.adapters.settings.CHAT_EXPERT_QUERY_MULTI_COUNT", 5):
            await adapter.rag_chat(
                query="公司的工资发放流程是什么？",
                top_k=3,
                chat_mode="expert",
            )

        runner_kwargs = agentic_runner.await_args.kwargs
        self.assertEqual(runner_kwargs["retrieval_profile"]["candidate_k"], 40)
        self.assertEqual(runner_kwargs["retrieval_profile"]["query_rewrite_count"], 5)
        self.assertTrue(runner_kwargs["retrieval_profile"]["enable_query_rewrite"])
        self.assertTrue(runner_kwargs["retrieval_profile"]["enable_rerank"])
        self.assertTrue(runner_kwargs["retrieval_profile"]["enable_context_compression"])

    async def test_fast_mode_streams_multimodal_rag_from_context(self):
        adapter = _build_mode_test_adapter()
        adapter._prepare_scoped_chat_context = AsyncMock(
            return_value={
                "intent": {"execution_mode": "multimodal_rag", "presentation_mode": "rag_answer", "use_rag": True, "reason": "fast"},
                "scoped_query": "公司内部报销流程是什么？",
                "documents": [{"id": "img-1", "document": "image", "metadata": {}, "score": 0.7}],
                "text_chunks": [],
                "generation_query": "公司内部报销流程是什么？",
                "generation_documents": [{"id": "img-1", "document": "image", "metadata": {}, "score": 0.7}],
                "generation_text_chunks": [],
                "generation_history": [],
                "combined_documents": [{"id": "img-1", "document": "image", "metadata": {}, "score": 0.7}],
                "streaming_ready": True,
            }
        )
        adapter._run_intent_chat = AsyncMock(side_effect=AssertionError("should use true streaming path"))

        chunks = []
        async for chunk, documents, intent in adapter.rag_chat_stream(
            query="公司内部报销流程是什么？",
            top_k=2,
            chat_mode="fast",
        ):
            chunks.append((chunk, documents, intent))

        self.assertEqual([item[0] for item in chunks], ["A", "B"])
        self.assertEqual(chunks[0][2]["execution_mode"], "multimodal_rag")
        adapter.rag_chain.astream_from_context.assert_called_once()
