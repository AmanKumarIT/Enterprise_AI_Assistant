"""
Embedding abstraction layer supporting both local SentenceTransformers
and OpenAI API embeddings with a unified interface.
"""
import logging
from abc import ABC, abstractmethod
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class BaseEmbedder(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of document texts."""
        ...

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query text."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding vector dimension."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier string."""
        ...


class SentenceTransformerEmbedder(BaseEmbedder):
    """Local embedding via SentenceTransformers (e.g. all-MiniLM-L6-v2, BGE, etc.)."""

    def __init__(self, model_name_or_path: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self._model_name = model_name_or_path
        logger.info("Loading SentenceTransformer model: %s", model_name_or_path)
        self._model = SentenceTransformer(model_name_or_path)
        self._dimension = self._model.get_sentence_embedding_dimension()
        logger.info("Model loaded. Dimension: %d", self._dimension)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        embeddings = self._model.encode(
            texts,
            show_progress_bar=False,
            normalize_embeddings=True,
            batch_size=64,
        )
        logger.info("Generated %d embeddings using SentenceTransformer (batch_size=64)", len(texts))
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        embedding = self._model.encode(
            [text],
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return embedding[0].tolist()

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name


class OpenAIEmbedder(BaseEmbedder):
    """OpenAI API-based embedding (text-embedding-3-small / ada-002 etc.)."""

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
    ):
        import openai

        self._client = openai.OpenAI(api_key=api_key)
        self._model = model
        self._dimension = dimensions
        logger.info("OpenAI embedder initialized with model: %s", model)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        batch_size = 100
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = self._client.embeddings.create(input=batch, model=self._model)
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
            logger.info("OpenAI: Processed batch %d/%d (%d vectors)", (i // batch_size) + 1, (len(texts) + batch_size - 1) // batch_size, len(batch_embeddings))
        
        logger.info("Total vectors generated via OpenAI: %d", len(all_embeddings))
        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        response = self._client.embeddings.create(input=[text], model=self._model)
        return response.data[0].embedding

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model


class HuggingFaceEmbedder(BaseEmbedder):
    """Hugging Face Hosted Inference API-based embedding."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        self._api_key = api_key
        self._model_name = model_name
        self._api_url = f"https://router.huggingface.co/pipeline/feature-extraction/{model_name}"
        self._dimension: Optional[int] = None
        logger.info("Hugging Face embedder initialized with model: %s", model_name)

    def _query_api(self, texts: List[str]) -> List[List[float]]:
        import requests

        response = requests.post(
            self._api_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"inputs": texts, "options": {"wait_for_model": True}},
        )
        if response.status_code != 200:
            logger.error("Hugging Face API error: %s", response.text)
            raise ValueError(f"Hugging Face API error: {response.text}")
        
        return response.json()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # Hugging Face Inference API usually handles batches well, 
        # but we'll batch locally to be safe and avoid timeouts
        batch_size = 32
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = self._query_api(batch)
            all_embeddings.extend(batch_embeddings)
            logger.info("HuggingFace: Processed batch %d/%d (%d vectors)", (i // batch_size) + 1, (len(texts) + batch_size - 1) // batch_size, len(batch_embeddings))
        
        if not self._dimension and all_embeddings:
            self._dimension = len(all_embeddings[0])
            
        logger.info("Total vectors generated via HuggingFace: %d", len(all_embeddings))
        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        embedding = self._query_api([text])[0]
        if not self._dimension:
            self._dimension = len(embedding)
        return embedding

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            # Lazy load dimension by embedding a dummy string
            self.embed_query("test")
        return self._dimension or 0

    @property
    def model_name(self) -> str:
        return self._model_name


def get_embedder(
    provider: str = "sentence_transformer",
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
) -> BaseEmbedder:
    """Factory function to create the appropriate embedder."""
    if provider == "openai":
        if not api_key:
            raise ValueError("OpenAI API key is required for OpenAI embedder")
        return OpenAIEmbedder(
            api_key=api_key,
            model=model_name or "text-embedding-3-small",
        )
    elif provider == "huggingface":
        if not api_key:
            raise ValueError("Hugging Face API key is required for Hugging Face embedder")
        return HuggingFaceEmbedder(
            api_key=api_key,
            model_name=model_name or "sentence-transformers/all-MiniLM-L6-v2",
        )
    
    return SentenceTransformerEmbedder(
        model_name_or_path=model_name or "all-MiniLM-L6-v2"
    )


def get_active_embedder() -> BaseEmbedder:
    """
    Centralized factory that returns the embedder configured in environment variables.
    Ensures consistent embedding across ingestion and retrieval.
    """
    from app.core.config import settings

    provider = settings.EMBEDDING_PROVIDER
    model = settings.EMBEDDING_MODEL
    
    api_key = None
    if provider == "openai":
        api_key = settings.OPENAI_API_KEY
    elif provider == "huggingface":
        api_key = settings.HUGGINGFACE_API_KEY
        
    return get_embedder(provider=provider, model_name=model, api_key=api_key)
