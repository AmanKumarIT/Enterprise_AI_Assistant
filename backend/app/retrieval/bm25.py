"""
BM25 lexical retrieval service.
Provides sparse keyword-based search using the Okapi BM25 algorithm
for hybrid retrieval alongside dense vector search.
"""
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

STOP_WORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
    "if", "in", "into", "is", "it", "no", "not", "of", "on", "or",
    "such", "that", "the", "their", "then", "there", "these", "they",
    "this", "to", "was", "will", "with", "what", "which", "who",
    "how", "when", "where", "why", "can", "do", "does", "did", "has",
    "have", "had", "from", "been", "were", "would", "could", "should",
})


def tokenize(text: str) -> List[str]:
    """Lowercase, strip punctuation, remove stop words."""
    tokens = re.findall(r"\b[a-zA-Z0-9]+\b", text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]


@dataclass
class BM25Document:
    """A document stored in the BM25 index."""
    doc_id: str
    tokens: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


class BM25Index:
    """
    In-memory BM25 index.
    Supports incremental document addition and scored retrieval.
    Uses Okapi BM25 with tunable k1 and b parameters.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: List[BM25Document] = []
        self.doc_freqs: Counter = Counter()
        self.doc_lengths: List[int] = []
        self.avg_doc_length: float = 0.0
        self.total_docs: int = 0
        self._inverted_index: Dict[str, List[int]] = {}

    def add_documents(
        self,
        doc_ids: List[str],
        texts: List[str],
        metadatas: Optional[List[Dict]] = None,
    ) -> None:
        """Add a batch of documents to the index."""
        if metadatas is None:
            metadatas = [{}] * len(texts)

        for doc_id, text, meta in zip(doc_ids, texts, metadatas):
            tokens = tokenize(text)
            doc_idx = len(self.documents)
            doc = BM25Document(doc_id=doc_id, tokens=tokens, metadata=meta)
            self.documents.append(doc)
            self.doc_lengths.append(len(tokens))

            seen_terms = set()
            for token in tokens:
                if token not in self._inverted_index:
                    self._inverted_index[token] = []
                self._inverted_index[token].append(doc_idx)
                if token not in seen_terms:
                    self.doc_freqs[token] += 1
                    seen_terms.add(token)

        self.total_docs = len(self.documents)
        self.avg_doc_length = (
            sum(self.doc_lengths) / self.total_docs if self.total_docs > 0 else 0.0
        )

    def search(
        self,
        query: str,
        top_k: int = 10,
        source_type: Optional[str] = None,
    ) -> List[Dict]:
        """
        Score all documents against the query using BM25.
        Returns top_k results sorted by score descending.
        """
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores: Dict[int, float] = {}

        for token in query_tokens:
            if token not in self._inverted_index:
                continue

            df = self.doc_freqs[token]
            idf = math.log(
                (self.total_docs - df + 0.5) / (df + 0.5) + 1.0
            )

            for doc_idx in self._inverted_index[token]:
                doc = self.documents[doc_idx]

                if source_type and doc.metadata.get("source_type") != source_type:
                    continue

                tf = doc.tokens.count(token)
                doc_len = self.doc_lengths[doc_idx]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * doc_len / self.avg_doc_length
                )
                score = idf * (numerator / denominator)

                scores[doc_idx] = scores.get(doc_idx, 0.0) + score

        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for doc_idx, score in sorted_results[:top_k]:
            doc = self.documents[doc_idx]
            results.append({
                "id": doc.doc_id,
                "score": score,
                "payload": doc.metadata,
            })

        return results

    def remove_documents(self, doc_ids: List[str]) -> None:
        """Remove documents by ID and rebuild index."""
        id_set = set(doc_ids)
        remaining = [d for d in self.documents if d.doc_id not in id_set]

        self.documents = []
        self.doc_freqs = Counter()
        self.doc_lengths = []
        self._inverted_index = {}

        if remaining:
            self.add_documents(
                doc_ids=[d.doc_id for d in remaining],
                texts=[" ".join(d.tokens) for d in remaining],
                metadatas=[d.metadata for d in remaining],
            )

    @property
    def size(self) -> int:
        return self.total_docs
