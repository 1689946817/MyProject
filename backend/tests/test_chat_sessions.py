import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.database import Base, get_db
from app.data import models as _models  # noqa: F401
from app.data import doc_models as _doc_models  # noqa: F401
from app.data import chat_models as _chat_models  # noqa: F401
from app.data.chat_models import ChatMessage, ChatSession
from app.main import create_app


class FakeAdapter:
    async def rag_chat(self, query, top_k=5, image=None, chat_history=None):
        if query == "doc-hit":
            return (
                "answer for doc-hit",
                [
                    {
                        "doc_id": "doc-1",
                        "chunk_index": 2,
                        "content": "document chunk content",
                        "metadata": {
                            "file_name": "report.pdf",
                            "file_path": "/tmp/report.pdf",
                        },
                        "score": 0.34,
                    }
                ],
            )
        if query == "mixed-hit":
            return (
                "answer for mixed-hit",
                [
                    {
                        "id": "img-9",
                        "document": "retrieved image doc",
                        "metadata": {
                            "file_path": "/tmp/mixed.jpg",
                            "filename": "mixed.jpg",
                        },
                        "score": 0.22,
                    },
                    {
                        "doc_id": "doc-9",
                        "chunk_index": 0,
                        "content": "chunk zero",
                        "metadata": {"file_path": "/tmp/doc9.pdf"},
                        "score": 0.55,
                    },
                ],
            )
        return (
            f"answer for {query}",
            [
                {
                    "id": "img-1",
                    "document": "retrieved doc",
                    "metadata": {"file_path": "/tmp/example.jpg", "filename": "example.jpg"},
                    "score": 0.12,
                }
            ],
        )

    async def rag_chat_stream(self, query, top_k=5, chat_history=None):
        yield (
            "stream part 1 ",
            [
                {
                    "id": "img-stream",
                    "document": "streamed retrieved doc",
                    "metadata": {"file_path": "/tmp/stream.jpg", "filename": "stream.jpg"},
                    "score": 0.44,
                }
            ],
        )
        yield (
            "stream part 2",
            [
                {
                    "doc_id": "stream-doc",
                    "chunk_index": 3,
                    "content": "stream chunk",
                    "metadata": {"file_name": "stream.pdf", "file_path": "/tmp/stream.pdf"},
                    "score": 0.66,
                }
            ],
        )


class TestChatSessions(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_chat.db")
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
        )
        self.SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

        self.app = create_app()

        def override_get_db():
            db = self.SessionTesting()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.adapter_patch = patch("app.api.routers.chat.get_langchain_adapter", return_value=FakeAdapter())
        self.adapter_patch.start()
        self.client = TestClient(self.app)

    def tearDown(self):
        self.adapter_patch.stop()
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_rag_chat_creates_session_and_persists_messages(self):
        response = self.client.post(
            "/api/rag/chat",
            data={"query": "hello", "top_k": "2"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("session_id", payload)
        self.assertEqual(payload["answer"], "answer for hello")
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(len(payload["sources"]), 1)
        self.assertEqual(payload["sources"][0]["source_type"], "image")
        self.assertEqual(payload["sources"][0]["source_id"], "img-1")

        db = self.SessionTesting()
        try:
            sessions = db.query(ChatSession).all()
            self.assertEqual(len(sessions), 1)
            messages = db.query(ChatMessage).order_by(ChatMessage.id.asc()).all()
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0].role, "user")
            self.assertEqual(messages[0].content, "hello")
            self.assertIsNone(messages[0].sources_json)
            self.assertEqual(messages[1].role, "assistant")
            self.assertEqual(messages[1].content, "answer for hello")
            self.assertIn('"source_id": "img-1"', messages[1].sources_json)
        finally:
            db.close()

    def test_rag_chat_appends_to_existing_session(self):
        first = self.client.post("/api/rag/chat", data={"query": "first"})
        session_id = first.json()["session_id"]

        second = self.client.post(
            "/api/rag/chat",
            data={"query": "second", "session_id": session_id},
        )
        self.assertEqual(second.status_code, 200)

        db = self.SessionTesting()
        try:
            messages = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id.asc())
                .all()
            )
            self.assertEqual(len(messages), 4)
            self.assertEqual([message.content for message in messages], [
                "first",
                "answer for first",
                "second",
                "answer for second",
            ])
            self.assertIsNone(messages[0].sources_json)
            self.assertEqual(messages[1].sources_json is not None, True)
            self.assertIsNone(messages[2].sources_json)
            self.assertEqual(messages[3].sources_json is not None, True)
        finally:
            db.close()

    def test_session_endpoints_support_create_list_get_rename_delete(self):
        created = self.client.post("/api/chat/sessions")
        self.assertEqual(created.status_code, 200)
        session_id = created.json()["id"]

        listed = self.client.get("/api/chat/sessions")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(listed.json()[0]["id"], session_id)

        renamed = self.client.patch(
            f"/api/chat/sessions/{session_id}",
            json={"title": "我的会话"},
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["id"], session_id)
        self.assertEqual(renamed.json()["title"], "我的会话")

        detail = self.client.get(f"/api/chat/sessions/{session_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["id"], session_id)
        self.assertEqual(detail.json()["title"], "我的会话")
        self.assertEqual(detail.json()["messages"], [])

        deleted = self.client.delete(f"/api/chat/sessions/{session_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json(), {"success": True})

        missing = self.client.get(f"/api/chat/sessions/{session_id}")
        self.assertEqual(missing.status_code, 404)

    def test_rag_chat_rejects_unknown_session_id(self):
        response = self.client.post(
            "/api/rag/chat",
            data={"query": "hello", "session_id": "missing-session"},
        )
        self.assertEqual(response.status_code, 404)

    def test_session_detail_returns_ordered_messages_with_sources(self):
        created = self.client.post("/api/chat/sessions")
        session_id = created.json()["id"]
        self.client.post("/api/rag/chat", data={"query": "one", "session_id": session_id})
        self.client.post("/api/rag/chat", data={"query": "doc-hit", "session_id": session_id})

        detail = self.client.get(f"/api/chat/sessions/{session_id}")
        self.assertEqual(detail.status_code, 200)
        messages = detail.json()["messages"]
        self.assertEqual([message["role"] for message in messages], ["user", "assistant", "user", "assistant"])
        self.assertEqual([message["content"] for message in messages], [
            "one",
            "answer for one",
            "doc-hit",
            "answer for doc-hit",
        ])
        self.assertEqual(messages[0]["sources"], [])
        self.assertEqual(messages[1]["sources"][0]["source_type"], "image")
        self.assertEqual(messages[3]["sources"][0]["source_type"], "document_chunk")
        self.assertEqual(messages[3]["sources"][0]["source_id"], "doc-1#chunk-2")

    def test_session_detail_gracefully_handles_invalid_sources_json(self):
        created = self.client.post("/api/chat/sessions")
        session_id = created.json()["id"]
        self.client.post("/api/rag/chat", data={"query": "hello", "session_id": session_id})

        db = self.SessionTesting()
        try:
            assistant_message = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id, ChatMessage.role == "assistant")
                .first()
            )
            assistant_message.sources_json = "not-json"
            db.add(assistant_message)
            db.commit()
        finally:
            db.close()

        detail = self.client.get(f"/api/chat/sessions/{session_id}")
        self.assertEqual(detail.status_code, 200)
        assistant_messages = [m for m in detail.json()["messages"] if m["role"] == "assistant"]
        self.assertEqual(assistant_messages[0]["sources"], [])

    def test_rag_chat_normalizes_mixed_hits(self):
        response = self.client.post("/api/rag/chat", data={"query": "mixed-hit"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["source_type"] for item in payload["sources"]], ["image", "document_chunk"])
        self.assertEqual(payload["sources"][1]["source_id"], "doc-9#chunk-0")

    def test_rag_chat_stream_returns_and_persists_sources(self):
        response = self.client.post("/api/rag/chat/stream", data={"query": "stream me"})
        self.assertEqual(response.status_code, 200)

        body = response.text
        self.assertIn('"type": "session"', body)
        self.assertIn('"type": "results"', body)
        self.assertIn('"sources":', body)
        self.assertIn('"source_id": "stream-doc#chunk-3"', body)
        self.assertIn('data: [DONE]', body)

        session_line = next(line for line in body.splitlines() if '"type": "session"' in line)
        session_payload = session_line[len("data: "):]
        session_id = __import__("json").loads(session_payload)["session_id"]

        detail = self.client.get(f"/api/chat/sessions/{session_id}")
        self.assertEqual(detail.status_code, 200)
        assistant_messages = [m for m in detail.json()["messages"] if m["role"] == "assistant"]
        self.assertEqual(len(assistant_messages), 1)
        self.assertEqual(assistant_messages[0]["sources"][0]["source_type"], "document_chunk")
        self.assertEqual(assistant_messages[0]["sources"][0]["source_id"], "stream-doc#chunk-3")


if __name__ == "__main__":
    unittest.main()
