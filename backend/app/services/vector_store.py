"""
Qdrant vector store service with collection management,
upsert, search, and namespace/workspace isolation.
"""
import logging
import uuid
from typing import List, Optional, Dict, Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    SearchParams,
    FilterSelector,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

COLLECTION_PREFIX = "eka_workspace_"


class VectorStoreService:
    """
    Wraps Qdrant operations and enforces workspace-level namespace isolation.
    Each workspace gets its own Qdrant collection.
    Uses lazy initialization so the app doesn't crash if Qdrant is briefly down.
    """

    def __init__(self):
        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            if settings.QDRANT_URL:
                self._client = QdrantClient(
                    url=settings.QDRANT_URL,
                    api_key=settings.QDRANT_API_KEY,
                )
                logger.info("Qdrant client connected to cloud at %s", settings.QDRANT_URL)
            else:
                self._client = QdrantClient(
                    host=settings.QDRANT_HOST,
                    port=settings.QDRANT_PORT,
                )
                logger.info(
                    "Qdrant client connected locally at %s:%s", 
                    settings.QDRANT_HOST, settings.QDRANT_PORT
                )
        return self._client

    def _collection_name(self, workspace_id: uuid.UUID) -> str:
        return f"{COLLECTION_PREFIX}{str(workspace_id).replace('-', '_')}"

    def ensure_collection(self, workspace_id: uuid.UUID, vector_size: int) -> None:
        """Create the workspace collection if it does not exist."""
        name = self._collection_name(workspace_id)
        collections = self.client.get_collections().collections
        existing_names = {c.name for c in collections}

        if name not in existing_names:
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )
            self.client.create_payload_index(
                collection_name=name,
                field_name="source_type",
                field_schema="keyword",
            )
            self.client.create_payload_index(
                collection_name=name,
                field_name="document_id",
                field_schema="keyword",
            )
            self.client.create_payload_index(
                collection_name=name,
                field_name="data_source_id",
                field_schema="keyword",
            )
            logger.info("Created Qdrant collection: %s (dim=%d)", name, vector_size)
        else:
            logger.debug("Qdrant collection already exists: %s", name)

    def upsert_vectors(
        self,
        workspace_id: uuid.UUID,
        ids: List[str],
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
    ) -> None:
        """Upsert embedding vectors with metadata payloads."""
        name = self._collection_name(workspace_id)
        points = [
            PointStruct(id=vid, vector=vec, payload=meta)
            for vid, vec, meta in zip(ids, vectors, payloads)
        ]
        logger.info("Starting upsert of %d vectors into collection: %s", len(points), name)
        batch_size = 256
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self.client.upsert(
                collection_name=name,
                points=batch,
            )
            logger.info("Successfully upserted batch %d/%d (%d vectors) into %s", (i // batch_size) + 1, (len(points) + batch_size - 1) // batch_size, len(batch), name)
        
        logger.info("Finalized upsert for %d vectors into %s", len(points), name)

    def search(
        self,
        workspace_id: uuid.UUID,
        query_vector: List[float],
        top_k: int = 10,
        source_type: Optional[str] = None,
        data_source_id: Optional[str] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors with optional metadata filtering."""
        name = self._collection_name(workspace_id)

        must_conditions = []
        if source_type:
            must_conditions.append(
                FieldCondition(key="source_type", match=MatchValue(value=source_type))
            )
        if data_source_id:
            must_conditions.append(
                FieldCondition(key="data_source_id", match=MatchValue(value=data_source_id))
            )

        query_filter = Filter(must=must_conditions) if must_conditions else None

        results = self.client.search(
            collection_name=name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=query_filter,
            score_threshold=score_threshold,
            search_params=SearchParams(exact=False, hnsw_ef=128),
        )

        return [
            {
                "id": str(hit.id),
                "score": hit.score,
                "payload": hit.payload,
            }
            for hit in results
        ]

    def delete_by_document(self, workspace_id: uuid.UUID, document_id: str) -> None:
        """Delete all vectors belonging to a specific document."""
        name = self._collection_name(workspace_id)
        self.client.delete(
            collection_name=name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id", match=MatchValue(value=document_id)
                        )
                    ]
                )
            ),
        )
        logger.info("Deleted vectors for document %s from %s", document_id, name)

    def delete_by_data_source(self, workspace_id: uuid.UUID, data_source_id: str) -> None:
        """Delete all vectors belonging to a specific data source."""
        name = self._collection_name(workspace_id)
        self.client.delete(
            collection_name=name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="data_source_id", match=MatchValue(value=data_source_id)
                        )
                    ]
                )
            ),
        )
        logger.info("Deleted vectors for data source %s from %s", data_source_id, name)

    def delete_collection(self, workspace_id: uuid.UUID) -> None:
        """Delete the entire workspace collection."""
        name = self._collection_name(workspace_id)
        self.client.delete_collection(collection_name=name)
        logger.info("Deleted Qdrant collection: %s", name)

    def get_collection_info(self, workspace_id: uuid.UUID) -> Dict[str, Any]:
        """Return collection stats (vector count, etc.)."""
        name = self._collection_name(workspace_id)
        info = self.client.get_collection(collection_name=name)
        return {
            "name": name,
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "status": info.status.value if info.status else "unknown",
        }


vector_store_service = VectorStoreService()
