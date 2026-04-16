"""
Hybrid retrieval engine.
Combines dense vector search (Qdrant) with BM25 sparse search,
applies metadata filtering, and merges scores using a configurable
alpha/beta weighting formula.
"""
import logging
import uuid
from typing import List, Dict, Any, Optional

from app.services.vector_store import vector_store_service
from app.services.embedding import BaseEmbedder
from app.retrieval.bm25 import BM25Index

logger = logging.getLogger(__name__)


class HybridRetriever:
    """
    Hybrid retrieval combining:
      - Dense retrieval via Qdrant cosine similarity
      - Sparse retrieval via BM25 lexical matching

    Hybrid Score = alpha * dense_score + beta * bm25_score

    Both scores are normalized to [0, 1] before merging.
    """

    def __init__(
        self,
        embedder: BaseEmbedder,
        bm25_index: BM25Index,
        alpha: float = 0.7,
        beta: float = 0.3,
    ):
        self.embedder = embedder
        self.bm25_index = bm25_index
        self.alpha = alpha
        self.beta = beta

    def retrieve(
        self,
        query: str,
        workspace_id: uuid.UUID,
        top_k: int = 20,
        source_type: Optional[str] = None,
        data_source_id: Optional[str] = None,
        dense_weight: Optional[float] = None,
        sparse_weight: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute hybrid retrieval:
        1. Dense search via Qdrant
        2. Sparse search via BM25
        3. Normalize and merge scores
        4. Return unified ranked results
        """
        alpha = dense_weight if dense_weight is not None else self.alpha
        beta = sparse_weight if sparse_weight is not None else self.beta

        dense_results = self._dense_search(
            query=query,
            workspace_id=workspace_id,
            top_k=top_k * 2,
            source_type=source_type,
            data_source_id=data_source_id,
        )

        sparse_results = self._sparse_search(
            query=query,
            top_k=top_k * 2,
            source_type=source_type,
        )

        merged = self._merge_results(dense_results, sparse_results, alpha, beta)

        merged.sort(key=lambda x: x["hybrid_score"], reverse=True)
        return merged[:top_k]

    def _dense_search(
        self,
        query: str,
        workspace_id: uuid.UUID,
        top_k: int,
        source_type: Optional[str] = None,
        data_source_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute dense vector search via Qdrant."""
        try:
            query_vector = self.embedder.embed_query(query)
            results = vector_store_service.search(
                workspace_id=workspace_id,
                query_vector=query_vector,
                top_k=top_k,
                source_type=source_type,
                data_source_id=data_source_id,
            )
            return results
        except Exception as e:
            logger.error("Dense search failed: %s", str(e))
            return []

    def _sparse_search(
        self,
        query: str,
        top_k: int,
        source_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute BM25 sparse search."""
        try:
            if self.bm25_index.size == 0:
                return []
            return self.bm25_index.search(
                query=query,
                top_k=top_k,
                source_type=source_type,
            )
        except Exception as e:
            logger.error("Sparse search failed: %s", str(e))
            return []

    def _merge_results(
        self,
        dense_results: List[Dict[str, Any]],
        sparse_results: List[Dict[str, Any]],
        alpha: float,
        beta: float,
    ) -> List[Dict[str, Any]]:
        """
        Merge dense and sparse results using Reciprocal Rank Fusion
        combined with score normalization.
        """
        dense_max = max((r["score"] for r in dense_results), default=1.0) or 1.0
        sparse_max = max((r["score"] for r in sparse_results), default=1.0) or 1.0

        merged_map: Dict[str, Dict[str, Any]] = {}

        for result in dense_results:
            rid = result["id"]
            norm_score = result["score"] / dense_max
            merged_map[rid] = {
                **result,
                "dense_score": norm_score,
                "sparse_score": 0.0,
                "hybrid_score": alpha * norm_score,
            }

        for result in sparse_results:
            rid = result["id"]
            norm_score = result["score"] / sparse_max

            if rid in merged_map:
                merged_map[rid]["sparse_score"] = norm_score
                merged_map[rid]["hybrid_score"] = (
                    alpha * merged_map[rid]["dense_score"]
                    + beta * norm_score
                )
            else:
                merged_map[rid] = {
                    **result,
                    "dense_score": 0.0,
                    "sparse_score": norm_score,
                    "hybrid_score": beta * norm_score,
                }

        return list(merged_map.values())
