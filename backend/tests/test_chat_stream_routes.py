import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.routers.chat import rag_chat_endpoint


class TestChatStreamRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_rag_chat_endpoint_keeps_json_mode_compatible(self):
        session = SimpleNamespace(id="session-json")
        adapter = MagicMock()
        adapter.rag_chat = AsyncMock(
            return_value=(
                "final answer",
                [
                    {
                        "id": "img-1",
                        "document": "image hit",
                        "metadata": {"file_path": "/tmp/a.png", "filename": "a.png"},
                        "score": 0.9,
                    }
                ],
                {
                    "presentation_mode": "rag_answer",
                    "execution_mode": "multimodal_rag",
                    "use_rag": True,
                    "retrieval_steps": [{"key": "retrieve", "label": "检索"}],
                },
            )
        )

        with patch("app.api.routers.chat.create_session", return_value=session), \
             patch("app.api.routers.chat.get_recent_history", return_value=[]), \
             patch("app.api.routers.chat.get_langchain_adapter", return_value=adapter), \
             patch("app.api.routers.chat.add_message") as mock_add_message, \
             patch("app.api.routers.chat.settings.EXPOSE_TIMINGS_IN_API", False):
            response = await rag_chat_endpoint(
                query="hello",
                top_k=None,
                enable_score_filter=None,
                min_relevance_score=None,
                execution_hint=None,
                source_scope_json=None,
                session_id=None,
                stream=False,
                image=None,
                db=MagicMock(),
            )

        self.assertEqual(response.answer, "final answer")
        self.assertEqual(response.session_id, "session-json")
        self.assertEqual(response.sources[0].source_id, "img-1")
        self.assertFalse(mock_add_message.call_args_list[0].kwargs["retrieval_params"]["stream"])

    async def test_rag_chat_endpoint_stream_mode_returns_sse_payload(self):
        session = SimpleNamespace(id="session-stream")
        adapter = MagicMock()

        async def _stream(**_kwargs):
            yield ("保修流程", [{"doc_id": "doc-1", "chunk_index": 1, "content": "保修流程需要先提交报修入口表单", "metadata": {"file_path": "/tmp/a.pdf", "file_name": "a.pdf", "page_number": 2}}], None)
            yield ("需要先提交报修入口表单", [{"doc_id": "doc-1", "chunk_index": 1, "content": "保修流程需要先提交报修入口表单", "metadata": {"file_path": "/tmp/a.pdf", "file_name": "a.pdf", "page_number": 2}}], {
                "presentation_mode": "rag_answer",
                "execution_mode": "multimodal_rag",
                "use_rag": True,
                "retrieval_steps": [{"key": "retrieve", "label": "检索"}],
            })

        adapter.rag_chat_stream = _stream

        with patch("app.api.routers.chat.create_session", return_value=session), \
             patch("app.api.routers.chat.get_recent_history", return_value=[]), \
             patch("app.api.routers.chat.get_langchain_adapter", return_value=adapter), \
             patch("app.api.routers.chat.add_message") as mock_add_message, \
             patch("app.api.routers.chat.settings.EXPOSE_TIMINGS_IN_API", False):
            response = await rag_chat_endpoint(
                query="hello",
                top_k=None,
                enable_score_filter=None,
                min_relevance_score=None,
                execution_hint=None,
                source_scope_json=None,
                session_id=None,
                stream=True,
                image=None,
                db=MagicMock(),
            )
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)

        payload = "".join(chunks)
        self.assertEqual(response.media_type, "text/event-stream")
        self.assertIn('"type": "session"', payload)
        self.assertIn('"type": "content"', payload)
        self.assertIn('"type": "results"', payload)
        self.assertIn('"citations"', payload)
        self.assertIn('"source_ids": ["doc-1#chunk-1"]', payload)
        self.assertIn("data: [DONE]", payload)
        self.assertTrue(mock_add_message.call_args_list[0].kwargs["retrieval_params"]["stream"])

    async def test_rag_chat_endpoint_stream_mode_normalizes_chunk_objects_and_persists_results(self):
        session = SimpleNamespace(id="session-stream-normalized")
        adapter = MagicMock()

        async def _stream(**_kwargs):
            yield (
                ChatGenerationChunk(message=AIMessageChunk(content="保修流程")),
                [{"doc_id": "doc-2", "chunk_index": 0, "content": "保修流程需要先提交报修入口表单", "metadata": {"file_path": "/tmp/b.pdf", "file_name": "b.pdf", "page_number": 1}}],
                None,
            )
            yield (
                ChatGenerationChunk(message=AIMessageChunk(content="需要先提交报修入口表单")),
                [{"doc_id": "doc-2", "chunk_index": 0, "content": "保修流程需要先提交报修入口表单", "metadata": {"file_path": "/tmp/b.pdf", "file_name": "b.pdf", "page_number": 1}}],
                {
                    "presentation_mode": "rag_answer",
                    "execution_mode": "multimodal_rag",
                    "use_rag": True,
                    "retrieval_steps": [{"key": "retrieve", "label": "检索"}],
                },
            )

        adapter.rag_chat_stream = _stream

        with patch("app.api.routers.chat.create_session", return_value=session), \
             patch("app.api.routers.chat.get_recent_history", return_value=[]), \
             patch("app.api.routers.chat.get_langchain_adapter", return_value=adapter), \
             patch("app.api.routers.chat.add_message") as mock_add_message, \
             patch("app.api.routers.chat.settings.EXPOSE_TIMINGS_IN_API", False):
            response = await rag_chat_endpoint(
                query="hello",
                top_k=None,
                enable_score_filter=None,
                min_relevance_score=None,
                execution_hint=None,
                source_scope_json=None,
                session_id=None,
                stream=True,
                image=None,
                db=MagicMock(),
            )
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)

        payload = "".join(chunks)
        self.assertIn('"type": "results"', payload)
        self.assertIn('"content": "保修流程"', payload)
        self.assertIn('"content": "需要先提交报修入口表单"', payload)
        self.assertEqual(mock_add_message.call_args_list[1].args[3], "保修流程需要先提交报修入口表单")
        self.assertIn('"citations"', payload)


if __name__ == "__main__":
    unittest.main()
