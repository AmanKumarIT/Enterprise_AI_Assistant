"""
Full RAG pipeline orchestrator.
Chains together all retrieval and generation components:
  Query → Classification → Source Routing → Retrieval →
  Reranking → Context Compression → LLM Generation →
  Citation Formatting → Confidence Scoring
"""
import logging
import re
import uuid
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from app.retrieval.query_classifier import QueryClassifier
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.reranker import get_reranker
from app.retrieval.context_compressor import ContextCompressor
from app.services.llm import LLMService, build_rag_messages
from app.services.embedding import BaseEmbedder
from app.retrieval.bm25 import BM25Index

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """A single source citation."""
    source_index: int
    source_type: str
    document_title: str
    source_uri: str
    chunk_index: Optional[int] = None
    retrieval_score: float = 0.0
    rerank_score: float = 0.0


@dataclass
class RAGResponse:
    """The complete response from the RAG pipeline."""
    answer: str
    citations: List[Citation] = field(default_factory=list)
    confidence_score: float = 0.0
    query_intent: str = ""
    target_sources: List[str] = field(default_factory=list)
    retrieval_metadata: Dict[str, Any] = field(default_factory=dict)
    processing_time_ms: float = 0.0


class RAGPipeline:
    """
    End-to-end RAG pipeline that orchestrates the complete flow
    from query to grounded, cited answer.
    """

    def __init__(
        self,
        embedder: BaseEmbedder,
        llm_service: LLMService,
        bm25_index: BM25Index,
        use_cross_encoder: bool = True,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
        max_retrieval_results: int = 20,
        max_context_tokens: int = 4000,
        max_reranked_results: int = 10,
    ):
        self.classifier = QueryClassifier()
        self.retriever = HybridRetriever(
            embedder=embedder,
            bm25_index=bm25_index,
            alpha=dense_weight,
            beta=sparse_weight,
        )
        self.reranker = get_reranker(use_cross_encoder=use_cross_encoder)
        self.compressor = ContextCompressor(
            max_tokens=max_context_tokens,
            max_chunks=max_reranked_results,
        )
        self.llm = llm_service
        self.max_retrieval_results = max_retrieval_results
        self.max_reranked_results = max_reranked_results

    def execute(
        self,
        query: str,
        workspace_id: uuid.UUID,
        source_type_filter: Optional[str] = None,
        data_source_id: Optional[str] = None,
    ) -> RAGResponse:
        """
        Execute the full RAG pipeline synchronously.

        Steps:
        1. Classify query intent and determine target sources
        2. Execute hybrid retrieval (dense + BM25)
        3. Rerank with cross-encoder
        4. Compress and select context
        5. Generate answer via LLM
        6. Extract citations and compute confidence
        """
        start_time = time.time()

        # Step 1: Query Classification
        classification = self.classifier.classify(query)
        target_sources = classification["target_sources"]
        query_intent = classification["intent"].value

        logger.info(
            "Query classified: intent=%s, sources=%s, confidence=%.2f",
            query_intent,
            target_sources,
            classification["confidence"],
        )

        # Step 2: Hybrid Retrieval
        all_results: List[Dict[str, Any]] = []

        if source_type_filter:
            results = self.retriever.retrieve(
                query=query,
                workspace_id=workspace_id,
                top_k=self.max_retrieval_results,
                source_type=source_type_filter,
                data_source_id=data_source_id,
            )
            all_results.extend(results)
        else:
            for source in target_sources:
                results = self.retriever.retrieve(
                    query=query,
                    workspace_id=workspace_id,
                    top_k=self.max_retrieval_results // max(len(target_sources), 1),
                    source_type=source,
                    data_source_id=data_source_id,
                )
                all_results.extend(results)

        if not all_results:
            return RAGResponse(
                answer="I couldn't find any relevant information in the connected data sources to answer your question. Please ensure the relevant data sources have been ingested.",
                confidence_score=0.0,
                query_intent=query_intent,
                target_sources=target_sources,
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        # Step 3: Reranking
        reranked = self.reranker.rerank(
            query=query,
            results=all_results,
            top_k=self.max_reranked_results,
        )

        # Step 4: Context Compression
        compressed = self.compressor.compress(reranked, query=query)
        context_text = self.compressor.format_context(compressed)

        # Step 5: LLM Generation
        messages = build_rag_messages(query=query, context=context_text)
        answer = self.llm.generate(messages)

        # Step 6: Citations & Confidence
        citations = self._extract_citations(compressed)
        confidence = self._compute_confidence(
            classification=classification,
            results=compressed,
            answer=answer,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        return RAGResponse(
            answer=answer,
            citations=citations,
            confidence_score=confidence,
            query_intent=query_intent,
            target_sources=target_sources,
            retrieval_metadata={
                "total_retrieved": len(all_results),
                "after_reranking": len(reranked),
                "after_compression": len(compressed),
                "classification_confidence": classification["confidence"],
                "classification_reasoning": classification["reasoning"],
            },
            processing_time_ms=elapsed_ms,
        )

    def _extract_citations(self, results: List[Dict[str, Any]]) -> List[Citation]:
        """Extract structured citations from the context results."""
        citations: List[Citation] = []
        for i, result in enumerate(results, 1):
            payload = result.get("payload", {})
            citations.append(
                Citation(
                    source_index=i,
                    source_type=payload.get("source_type", "Unknown"),
                    document_title=payload.get("document_title", "Untitled"),
                    source_uri=payload.get("source_uri", ""),
                    chunk_index=payload.get("chunk_index"),
                    retrieval_score=result.get("hybrid_score", result.get("score", 0.0)),
                    rerank_score=result.get("rerank_score", 0.0),
                )
            )
        return citations

    def _compute_confidence(
        self,
        classification: Dict[str, Any],
        results: List[Dict[str, Any]],
        answer: str,
    ) -> float:
        """
        Compute a confidence score for the answer based on:
          - Classification confidence
          - Retrieval score quality
          - Number of supporting sources
          - Answer quality signals
        """
        if not results:
            return 0.0

        classification_conf = classification.get("confidence", 0.5)

        retrieval_scores = [
            r.get("rerank_score", r.get("hybrid_score", r.get("score", 0.0)))
            for r in results
        ]
        avg_retrieval = sum(retrieval_scores) / len(retrieval_scores) if retrieval_scores else 0.0
        top_retrieval = max(retrieval_scores) if retrieval_scores else 0.0

        source_types = set(
            r.get("payload", {}).get("source_type", "") for r in results
        )
        source_diversity = min(len(source_types) / 3.0, 1.0)

        hedging_phrases = [
            "i'm not sure", "i don't have enough",
            "no relevant information", "cannot determine",
            "unclear", "insufficient",
        ]
        answer_lower = answer.lower()
        has_hedging = any(phrase in answer_lower for phrase in hedging_phrases)
        has_citations = "[source" in answer_lower

        answer_quality = 0.7
        if has_hedging:
            answer_quality = 0.2
        elif has_citations:
            answer_quality = 0.9

        confidence = (
            0.25 * classification_conf
            + 0.30 * min(top_retrieval, 1.0)
            + 0.15 * min(avg_retrieval, 1.0)
            + 0.10 * source_diversity
            + 0.20 * answer_quality
        )

        return round(min(max(confidence, 0.0), 1.0), 3)
