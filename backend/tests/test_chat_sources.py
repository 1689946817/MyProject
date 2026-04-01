import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.routers.chat import _normalize_chat_sources, _to_chat_message_out
from app.data.chat_models import ChatMessage


class TestChatSources(unittest.TestCase):
    def test_normalize_image_hit(self):
        sources = _normalize_chat_sources(
            [
                {
                    "id": "img-1",
                    "document": "image description",
                    "metadata": {
                        "file_path": "/tmp/cat.jpg",
                        "filename": "cat.jpg",
                        "extra": "value",
                    },
                    "score": 0.1,
                }
            ]
        )

        self.assertEqual(len(sources), 1)
        source = sources[0]
        self.assertEqual(source.source_type, "image")
        self.assertEqual(source.source_id, "img-1")
        self.assertEqual(source.title, "cat.jpg")
        self.assertEqual(source.file_path, "/tmp/cat.jpg")
        self.assertEqual(source.content, "image description")
        self.assertEqual(source.score, 0.1)
        self.assertEqual(source.metadata["extra"], "value")

    def test_normalize_document_chunk_hit(self):
        sources = _normalize_chat_sources(
            [
                {
                    "doc_id": "doc-7",
                    "chunk_index": 4,
                    "content": "chunk body",
                    "metadata": {
                        "file_name": "paper.pdf",
                        "file_path": "/tmp/paper.pdf",
                    },
                    "score": 0.2,
                }
            ]
        )

        self.assertEqual(len(sources), 1)
        source = sources[0]
        self.assertEqual(source.source_type, "document_chunk")
        self.assertEqual(source.source_id, "doc-7#chunk-4")
        self.assertEqual(source.title, "paper.pdf")
        self.assertEqual(source.file_path, "/tmp/paper.pdf")
        self.assertEqual(source.content, "chunk body")
        self.assertEqual(source.metadata["doc_id"], "doc-7")
        self.assertEqual(source.metadata["chunk_index"], 4)

    def test_normalize_mixed_hits(self):
        sources = _normalize_chat_sources(
            [
                {
                    "id": "img-2",
                    "document": "img body",
                    "metadata": {"file_path": "/tmp/2.jpg"},
                    "score": 0.3,
                },
                {
                    "doc_id": "doc-2",
                    "chunk_index": 1,
                    "content": "doc body",
                    "metadata": {},
                    "score": 0.4,
                },
            ]
        )

        self.assertEqual([item.source_type for item in sources], ["image", "document_chunk"])
        self.assertEqual(sources[0].title, "2.jpg")
        self.assertEqual(sources[1].title, "doc-2")

    def test_to_chat_message_out_returns_empty_sources_for_user_and_invalid_json(self):
        message = ChatMessage(
            id=1,
            session_id="session-1",
            role="user",
            content="hello",
            has_image=False,
            sources_json="not-json",
            created_at=datetime.utcnow(),
        )

        output = _to_chat_message_out(message)
        self.assertEqual(output.sources, [])

    def test_to_chat_message_out_loads_sources(self):
        message = ChatMessage(
            id=2,
            session_id="session-1",
            role="assistant",
            content="answer",
            has_image=False,
            sources_json='[{"source_type":"image","source_id":"img-3","title":"three.jpg","file_path":"/tmp/three.jpg","content":"desc","score":0.9,"metadata":{"k":"v"}}]',
            created_at=datetime.utcnow(),
        )

        output = _to_chat_message_out(message)
        self.assertEqual(len(output.sources), 1)
        self.assertEqual(output.sources[0].source_id, "img-3")
        self.assertEqual(output.sources[0].metadata["k"], "v")


if __name__ == "__main__":
    unittest.main()
