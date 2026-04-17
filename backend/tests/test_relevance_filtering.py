import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.retrieval.relevance import (
    annotate_relevance,
    filter_by_relevance,
    resolve_effective_relevance_score,
)


class TestRelevanceFiltering(unittest.TestCase):
    def test_resolve_effective_relevance_prefers_rerank_then_rrf_then_score(self):
        score, source = resolve_effective_relevance_score(
            {"score": 0.2, "rrf_score": 0.4, "rerank_score": 0.9}
        )
        self.assertEqual(score, 0.9)
        self.assertEqual(source, "rerank")

    def test_annotate_relevance_writes_fields_to_payload_and_metadata(self):
        payload = {"score": 0.33, "metadata": {}}
        annotate_relevance(payload)
        self.assertEqual(payload["relevance_score"], 0.33)
        self.assertEqual(payload["score_source"], "vector")
        self.assertEqual(payload["metadata"]["relevance_score"], 0.33)
        self.assertEqual(payload["metadata"]["score_source"], "vector")

    def test_filter_by_relevance_only_keeps_items_above_threshold(self):
        items = [
            {"id": "a", "rerank_score": 0.91, "metadata": {}},
            {"id": "b", "rrf_score": 0.41, "metadata": {}},
            {"id": "c", "score": 0.71, "metadata": {}},
        ]
        filtered = filter_by_relevance(items, enabled=True, min_score=0.7)
        self.assertEqual([item["id"] for item in filtered], ["a", "b", "c"])

    def test_filter_by_relevance_only_applies_threshold_to_rerank_score(self):
        items = [
            {"id": "a", "rerank_score": 0.91, "metadata": {}},
            {"id": "b", "rerank_score": 0.21, "metadata": {}},
            {"id": "c", "score": 0.99, "metadata": {}},
        ]
        filtered = filter_by_relevance(items, enabled=True, min_score=0.7)
        self.assertEqual([item["id"] for item in filtered], ["a", "c"])


if __name__ == "__main__":
    unittest.main()
