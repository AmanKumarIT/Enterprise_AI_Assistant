"""
Base ingestion pipeline defining the contract all source-specific
pipelines must fulfill, plus shared orchestration logic.
"""
import logging
import uuid
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.document import (
    Document,
    DocumentChunk,
    DataSource,
    IngestionJob,
    IngestionStatus,
    SourceType,
)
from app.services.embedding import BaseEmbedder
from app.services.chunking import Chunk
from app.services.vector_store import vector_store_service

logger = logging.getLogger(__name__)


class RawDocument:
    """Intermediate representation of a document before embedding."""

    def __init__(
        self,
        title: str,
        content: str,
        source_uri: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        mime_type: str = "text/plain",
    ):
        self.title = title
        self.content = content
        self.source_uri = source_uri
        self.metadata = metadata or {}
        self.mime_type = mime_type
        self.content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()


class BaseIngestionPipeline(ABC):
    """
    All source-specific pipelines inherit from this class and implement
    extract_documents(). The base class handles chunking, embedding,
    vector upsert, and DB bookkeeping.
    """

    def __init__(
        self,
        db: AsyncSession,
        embedder: BaseEmbedder,
        workspace_id: uuid.UUID,
        data_source: DataSource,
    ):
        self.db = db
        self.embedder = embedder
        self.workspace_id = workspace_id
        self.data_source = data_source

    @abstractmethod
    async def extract_documents(self) -> List[RawDocument]:
        """Pull raw documents from the external source."""
        ...

    @abstractmethod
    def get_chunker(self):
        """Return the appropriate chunker for this source type."""
        ...

    async def run(self, job: IngestionJob, force_reindex: bool = False) -> IngestionJob:
        """
        Full orchestration:
        1. Extract documents from source
        2. Deduplicate via content hash
        3. Chunk
        4. Embed
        5. Store vectors in Qdrant
        6. Persist metadata in Postgres
        """
        job.status = IngestionStatus.IN_PROGRESS
        job.started_at = datetime.now(timezone.utc)
        self.db.add(job)
        await self.db.commit()

        try:
            raw_docs = await self.extract_documents()
            job.total_documents = len(raw_docs)
            await self.db.commit()

            vector_store_service.ensure_collection(
                self.workspace_id, self.embedder.dimension
            )

            chunker = self.get_chunker()
            processed = 0
            failed = 0

            for raw_doc in raw_docs:
                try:
                    existing = await self._find_existing_document(raw_doc)
                    if existing and existing.content_hash == raw_doc.content_hash and not force_reindex:
                        processed += 1
                        continue

                    if existing:
                        vector_store_service.delete_by_document(
                            self.workspace_id, str(existing.id)
                        )
                        await self._delete_chunks(existing.id)
                        doc = existing
                        doc.version += 1
                        doc.content_hash = raw_doc.content_hash
                    else:
                        doc = Document(
                            data_source_id=self.data_source.id,
                            workspace_id=self.workspace_id,
                            title=raw_doc.title,
                            content_hash=raw_doc.content_hash,
                            source_uri=raw_doc.source_uri,
                            source_type=self.data_source.source_type,
                            metadata_=raw_doc.metadata,
                            file_size_bytes=len(raw_doc.content.encode("utf-8")),
                            mime_type=raw_doc.mime_type,
                            embedding_model=self.embedder.model_name,
                        )
                        self.db.add(doc)
                        await self.db.flush()

                    chunks: List[Chunk] = chunker.chunk_text(
                        raw_doc.content,
                        metadata={
                            "source_type": self.data_source.source_type.value,
                            "document_title": raw_doc.title,
                            "source_uri": raw_doc.source_uri,
                        },
                    ) if hasattr(chunker, "chunk_text") else chunker.chunk_code(
                        raw_doc.content,
                        filename=raw_doc.source_uri or raw_doc.title,
                        metadata={
                            "source_type": self.data_source.source_type.value,
                            "document_title": raw_doc.title,
                            "source_uri": raw_doc.source_uri,
                        },
                    )
                    logger.info("Created %d chunks for document: %s", len(chunks), raw_doc.title)

                    if not chunks:
                        processed += 1
                        continue

                    texts = [c.content for c in chunks]
                    embeddings = self.embedder.embed_documents(texts)

                    vector_ids: List[str] = []
                    db_chunks: List[DocumentChunk] = []
                    payloads: List[Dict[str, Any]] = []

                    for chunk, embedding in zip(chunks, embeddings):
                        vid = str(uuid.uuid4())
                        vector_ids.append(vid)

                        db_chunk = DocumentChunk(
                            document_id=doc.id,
                            chunk_index=chunk.index,
                            content=chunk.content,
                            token_count=chunk.token_count,
                            metadata_=chunk.metadata,
                            vector_id=vid,
                        )
                        db_chunks.append(db_chunk)

                        payload = {
                            "document_id": str(doc.id),
                            "data_source_id": str(self.data_source.id),
                            "workspace_id": str(self.workspace_id),
                            "source_type": self.data_source.source_type.value,
                            "chunk_index": chunk.index,
                            "document_title": raw_doc.title,
                            "source_uri": raw_doc.source_uri,
                            "content": chunk.content[:500],
                        }
                        payloads.append(payload)

                    vector_store_service.upsert_vectors(
                        workspace_id=self.workspace_id,
                        ids=vector_ids,
                        vectors=embeddings,
                        payloads=payloads,
                    )

                    self.db.add_all(db_chunks)
                    doc.chunk_count = len(db_chunks)
                    await self.db.commit()
                    processed += 1

                except Exception as doc_err:
                    logger.exception(
                        "Failed to process document '%s'",
                        raw_doc.title,
                    )
                    failed += 1
                    await self.db.rollback()

            job.processed_documents = processed
            job.failed_documents = failed
            job.status = (
                IngestionStatus.COMPLETED
                if failed == 0
                else IngestionStatus.PARTIAL
            )
            job.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            logger.error("Ingestion job %s failed: %s", job.id, str(e), exc_info=True)
            job.status = IngestionStatus.FAILED
            job.error_message = str(e)[:2000]
            job.completed_at = datetime.now(timezone.utc)

        self.db.add(job)
        await self.db.commit()
        return job

    async def _find_existing_document(self, raw_doc: RawDocument) -> Optional[Document]:
        stmt = select(Document).where(
            Document.data_source_id == self.data_source.id,
            Document.source_uri == raw_doc.source_uri,
            Document.is_active == True,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _delete_chunks(self, document_id: uuid.UUID) -> None:
        stmt = select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        result = await self.db.execute(stmt)
        chunks = result.scalars().all()
        for chunk in chunks:
            await self.db.delete(chunk)
        await self.db.flush()
