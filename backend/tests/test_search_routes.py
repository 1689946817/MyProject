import os
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import create_app


class FakeSearchAdapter:
    def __init__(self):
        self.text_calls = []
        self.image_calls = []

    async def text_to_image_search(
        self,
        query,
        top_k=10,
        fast=False,
        enable_score_filter=False,
        min_relevance_score=None,
    ):
        self.text_calls.append(
            {
                "query": query,
                "top_k": top_k,
                "fast": fast,
                "enable_score_filter": enable_score_filter,
                "min_relevance_score": min_relevance_score,
            }
        )
        return [
            {
                "id": "img-a",
                "document": "hit a",
                "metadata": {"file_path": "/tmp/a.jpg"},
                "score": 0.11,
                "relevance_score": 0.91,
                "score_source": "rerank",
            }
        ]

    async def image_to_image_search(
        self,
        file,
        top_k=10,
        fast=False,
        enable_score_filter=False,
        min_relevance_score=None,
    ):
        self.image_calls.append(
            {
                "filename": getattr(file, "filename", ""),
                "top_k": top_k,
                "fast": fast,
                "enable_score_filter": enable_score_filter,
                "min_relevance_score": min_relevance_score,
            }
        )
        return (
            [
                {
                    "id": "img-b",
                    "document": "hit b",
                    "metadata": {"file_path": "/tmp/b.jpg"},
                    "score": 0.25,
                    "relevance_score": 0.78,
                    "score_source": "vector",
                }
            ],
            "query desc",
        )


class TestSearchRoutes(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.fake_adapter = FakeSearchAdapter()
        self.adapter_patch = patch("app.api.routers.search.get_langchain_adapter", return_value=self.fake_adapter)
        self.adapter_patch.start()
        self.client = TestClient(self.app)

    def tearDown(self):
        self.adapter_patch.stop()

    def test_text_to_image_supports_filter_params_and_response_fields(self):
        response = self.client.post(
            "/api/search/text-to-image",
            json={
                "query": "router",
                "top_k": 3,
                "enable_score_filter": True,
                "min_relevance_score": 0.6,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["relevance_score"], 0.91)
        self.assertEqual(payload["results"][0]["score_source"], "rerank")
        self.assertEqual(self.fake_adapter.text_calls[0]["top_k"], 3)
        self.assertTrue(self.fake_adapter.text_calls[0]["enable_score_filter"])
        self.assertEqual(self.fake_adapter.text_calls[0]["min_relevance_score"], 0.6)

    def test_image_to_image_uses_route_defaults_when_params_omitted(self):
        response = self.client.post(
            "/api/search/image-to-image",
            files={"file": ("demo.jpg", b"fake-bytes", "image/jpeg")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["relevance_score"], 0.78)
        self.assertEqual(payload["results"][0]["score_source"], "vector")
        self.assertEqual(self.fake_adapter.image_calls[0]["top_k"], 10)
        self.assertFalse(self.fake_adapter.image_calls[0]["enable_score_filter"])
        self.assertEqual(self.fake_adapter.image_calls[0]["min_relevance_score"], 0.0)

    def test_image_to_image_accepts_form_control_params(self):
        response = self.client.post(
            "/api/search/image-to-image",
            files={"file": ("demo.jpg", b"fake-bytes", "image/jpeg")},
            data={
                "top_k": "3",
                "enable_score_filter": "true",
                "min_relevance_score": "0.6",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake_adapter.image_calls[0]["top_k"], 3)
        self.assertTrue(self.fake_adapter.image_calls[0]["enable_score_filter"])
        self.assertEqual(self.fake_adapter.image_calls[0]["min_relevance_score"], 0.6)


if __name__ == "__main__":
    unittest.main()
