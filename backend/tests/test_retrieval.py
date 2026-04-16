"""
Unit tests for retrieval components (BM25, query classifier, context compressor).
These do NOT require external services.
"""
import pytest
from app.retrieval.bm25 import BM25Index
from app.retrieval.query_classifier import QueryClassifier, QueryIntent
from app.retrieval.context_compressor import ContextCompressor


class TestBM25:
    def test_empty_index_search(self):
        idx = BM25Index()
        results = idx.search("hello world")
        assert results == []

    def test_add_and_search(self):
        idx = BM25Index()
        idx.add_documents(
            doc_ids=["d1", "d2", "d3"],
            texts=[
                "Python is a great programming language",
                "JavaScript is used for web development",
                "Python and JavaScript are both popular",
            ],
        )
        assert idx.size == 3

        results = idx.search("Python programming", top_k=2)
        assert len(results) <= 2
        assert results[0]["id"] == "d1"

    def test_source_type_filter(self):
        idx = BM25Index()
        idx.add_documents(
            doc_ids=["d1", "d2"],
            texts=["Sales report Q1", "Backend authentication flow"],
            metadatas=[{"source_type": "PDF"}, {"source_type": "GITHUB"}],
        )
        results = idx.search("report", source_type="PDF")
        assert len(results) == 1
        assert results[0]["id"] == "d1"

    def test_remove_documents(self):
        idx = BM25Index()
        idx.add_documents(
            doc_ids=["d1", "d2"],
            texts=["First document", "Second document"],
        )
        idx.remove_documents(["d1"])
        assert idx.size == 1
        results = idx.search("First")
        assert len(results) == 0


class TestQueryClassifier:
    def setup_method(self):
        self.classifier = QueryClassifier()

    def test_code_query(self):
        result = self.classifier.classify("Explain the authentication flow in the backend repo")
        assert result["intent"] in (QueryIntent.CODE_SEARCH, QueryIntent.MULTI_SOURCE)
        assert "GITHUB" in result["target_sources"]

    def test_slack_query(self):
        result = self.classifier.classify("What did engineering discuss about database migration in Slack?")
        assert result["intent"] in (QueryIntent.SLACK_SEARCH, QueryIntent.MULTI_SOURCE)
        assert "SLACK" in result["target_sources"]

    def test_jira_query(self):
        result = self.classifier.classify("Show Jira bugs related to checkout failures")
        assert "JIRA" in result["target_sources"]

    def test_multi_source_query(self):
        result = self.classifier.classify("Compare customer complaints from Slack with Jira bugs")
        assert result["intent"] == QueryIntent.MULTI_SOURCE

    def test_general_query(self):
        result = self.classifier.classify("Tell me about the weather")
        assert result["intent"] == QueryIntent.GENERAL

    def test_confidence_range(self):
        result = self.classifier.classify("any query")
        assert 0 <= result["confidence"] <= 1


class TestContextCompressor:
    def setup_method(self):
        self.compressor = ContextCompressor(max_tokens=500, max_chunks=5)

    def test_empty_results(self):
        assert self.compressor.compress([]) == []

    def test_deduplication(self):
        results = [
            {"payload": {"content": "Same content here", "source_type": "PDF"}, "score": 0.9},
            {"payload": {"content": "Same content here", "source_type": "PDF"}, "score": 0.8},
            {"payload": {"content": "Different content entirely", "source_type": "SLACK"}, "score": 0.7},
        ]
        compressed = self.compressor.compress(results)
        assert len(compressed) <= 2

    def test_source_diversity(self):
        results = [
            {"payload": {"content": f"PDF doc {i}", "source_type": "PDF"}, "score": 0.9 - i * 0.1}
            for i in range(10)
        ]
        results += [
            {"payload": {"content": "Slack message", "source_type": "SLACK"}, "score": 0.5}
        ]
        compressed = self.compressor.compress(results)
        source_types = {r["payload"]["source_type"] for r in compressed}
        assert "SLACK" in source_types

    def test_format_context(self):
        results = [
            {
                "payload": {
                    "content": "Test content",
                    "source_type": "PDF",
                    "document_title": "Test Doc",
                    "source_uri": "/test.pdf",
                },
            }
        ]
        context = self.compressor.format_context(results)
        assert "Test content" in context
        assert "Source 1" in context
        assert "PDF" in context
