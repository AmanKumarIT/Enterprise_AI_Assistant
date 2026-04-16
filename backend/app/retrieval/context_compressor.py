"""
Context compressor.
Takes ranked retrieval results and compresses/selects the most
relevant context to fit within the LLM's context window while
maximizing information density.
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ContextCompressor:
    """
    Compresses and selects retrieval results to fit within a token budget.
    Strategies:
      - Top-K selection by score
      - Deduplication by content similarity
      - Token-budget aware truncation
      - Source diversity enforcement
    """

    def __init__(
        self,
        max_tokens: int = 4000,
        max_chunks: int = 15,
        diversity_factor: float = 0.3,
    ):
        self.max_tokens = max_tokens
        self.max_chunks = max_chunks
        self.diversity_factor = diversity_factor

    def compress(
        self,
        results: List[Dict[str, Any]],
        query: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Compress retrieval results to fit the context window.

        Steps:
          1. Deduplicate near-identical chunks
          2. Enforce source diversity
          3. Truncate to token budget
          4. Return selected context chunks
        """
        if not results:
            return []

        deduped = self._deduplicate(results)
        diverse = self._enforce_diversity(deduped)
        truncated = self._truncate_to_budget(diverse)

        return truncated

    def _deduplicate(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove near-duplicate chunks based on content overlap."""
        seen_hashes: set = set()
        deduped: List[Dict[str, Any]] = []

        for result in results:
            content = result.get("payload", {}).get("content", "")
            content_sig = self._content_signature(content)

            if content_sig not in seen_hashes:
                seen_hashes.add(content_sig)
                deduped.append(result)

        return deduped

    def _content_signature(self, text: str) -> str:
        """Create a fuzzy signature for deduplication."""
        words = text.lower().split()
        if len(words) < 10:
            return " ".join(words)
        sample = words[:5] + words[len(words)//2 : len(words)//2 + 5] + words[-5:]
        return " ".join(sample)

    def _enforce_diversity(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Ensure results include content from multiple sources
        when available, rather than being dominated by one source.
        """
        source_buckets: Dict[str, List[Dict[str, Any]]] = {}
        for result in results:
            source = result.get("payload", {}).get("source_type", "unknown")
            if source not in source_buckets:
                source_buckets[source] = []
            source_buckets[source].append(result)

        if len(source_buckets) <= 1:
            return results[:self.max_chunks]

        diverse_results: List[Dict[str, Any]] = []
        max_per_source = max(
            int(self.max_chunks * (1 - self.diversity_factor)),
            2,
        )

        for source, items in source_buckets.items():
            diverse_results.extend(items[:max_per_source])

        diverse_results.sort(
            key=lambda x: x.get("rerank_score", x.get("hybrid_score", x.get("score", 0))),
            reverse=True,
        )

        return diverse_results[:self.max_chunks]

    def _truncate_to_budget(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Truncate results to fit within the token budget."""
        selected: List[Dict[str, Any]] = []
        total_tokens = 0

        for result in results:
            content = result.get("payload", {}).get("content", "")
            estimated_tokens = len(content.split()) * 4 // 3

            if total_tokens + estimated_tokens > self.max_tokens:
                remaining_budget = self.max_tokens - total_tokens
                if remaining_budget > 100:
                    words = content.split()
                    truncated_words = words[: int(remaining_budget * 3 // 4)]
                    result = result.copy()
                    result["payload"] = {**result.get("payload", {})}
                    result["payload"]["content"] = " ".join(truncated_words) + "..."
                    result["truncated"] = True
                    selected.append(result)
                break

            selected.append(result)
            total_tokens += estimated_tokens

        return selected

    def format_context(self, results: List[Dict[str, Any]]) -> str:
        """Format compressed results into a single context string for the LLM."""
        context_parts: List[str] = []

        for i, result in enumerate(results, 1):
            payload = result.get("payload", {})
            source_type = payload.get("source_type", "Unknown")
            title = payload.get("document_title", "Untitled")
            content = payload.get("content", "")
            source_uri = payload.get("source_uri", "")

            header = f"[Source {i}] ({source_type}) {title}"
            if source_uri:
                header += f" | {source_uri}"

            context_parts.append(f"{header}\n{content}")

        return "\n\n---\n\n".join(context_parts)
