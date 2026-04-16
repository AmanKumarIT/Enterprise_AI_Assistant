"""
Cross-encoder reranker service.
Re-scores candidate results using a cross-encoder model for
higher precision after initial retrieval.
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """
    Reranks retrieval results using a cross-encoder model.
    Supports models like cross-encoder/ms-marco-MiniLM-L-6-v2
    or BAAI/bge-reranker-base.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        from sentence_transformers import CrossEncoder

        self._model_name = model_name
        logger.info("Loading cross-encoder model: %s", model_name)
        self._model = CrossEncoder(model_name, max_length=512)
        logger.info("Cross-encoder model loaded.")

    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        content_key: str = "content",
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Rerank results by scoring each (query, document) pair
        through the cross-encoder.

        Args:
            query: The user query.
            results: List of result dicts, each containing a payload
                     with text content.
            content_key: Key in payload containing the text to score against.
            top_k: Maximum number of results to return after reranking.

        Returns:
            Reranked list of result dicts with updated 'rerank_score'.
        """
        if not results:
            return results

        pairs = []
        valid_indices = []
        for i, result in enumerate(results):
            text = result.get("payload", {}).get(content_key, "")
            if text:
                pairs.append((query, text))
                valid_indices.append(i)

        if not pairs:
            return results

        scores = self._model.predict(pairs, show_progress_bar=False)

        reranked = []
        for idx, score in zip(valid_indices, scores):
            result = results[idx].copy()
            result["rerank_score"] = float(score)
            result["original_score"] = result.get("score", 0.0)
            reranked.append(result)

        reranked.sort(key=lambda x: x["rerank_score"], reverse=True)

        if top_k:
            reranked = reranked[:top_k]

        return reranked


class LightweightReranker:
    """
    Fallback reranker using keyword overlap scoring
    when no cross-encoder model is available.
    """

    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        content_key: str = "content",
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        import re

        query_tokens = set(re.findall(r"\b\w+\b", query.lower()))

        reranked = []
        for result in results:
            text = result.get("payload", {}).get(content_key, "")
            doc_tokens = set(re.findall(r"\b\w+\b", text.lower()))
            overlap = len(query_tokens & doc_tokens)
            total = len(query_tokens) if query_tokens else 1

            result_copy = result.copy()
            result_copy["rerank_score"] = overlap / total
            result_copy["original_score"] = result.get("score", 0.0)
            reranked.append(result_copy)

        reranked.sort(key=lambda x: x["rerank_score"], reverse=True)

        if top_k:
            reranked = reranked[:top_k]

        return reranked


def get_reranker(use_cross_encoder: bool = True, model_name: str = None):
    """Factory function for reranker selection."""
    if use_cross_encoder:
        try:
            return CrossEncoderReranker(
                model_name=model_name or "cross-encoder/ms-marco-MiniLM-L-6-v2"
            )
        except Exception as e:
            logger.warning("Cross-encoder unavailable, falling back: %s", str(e))
            return LightweightReranker()
    return LightweightReranker()
