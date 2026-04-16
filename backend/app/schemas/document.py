from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.models.document import SourceType, IngestionStatus


class DataSourceBase(BaseModel):
    name: str
    source_type: SourceType
    connection_config: Optional[Dict[str, Any]] = None
    is_active: bool = True
    sync_frequency_minutes: Optional[int] = None


class DataSourceCreate(DataSourceBase):
    pass


class DataSourceUpdate(BaseModel):
    name: Optional[str] = None
    connection_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    sync_frequency_minutes: Optional[int] = None


class DataSource(DataSourceBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    created_by: uuid.UUID
    last_sync_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentBase(BaseModel):
    title: str
    source_type: SourceType
    source_uri: Optional[str] = None
    metadata_: Optional[Dict[str, Any]] = None


class DocumentCreate(DocumentBase):
    data_source_id: uuid.UUID


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    metadata_: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class Document(DocumentBase):
    id: uuid.UUID
    data_source_id: uuid.UUID
    workspace_id: uuid.UUID
    content_hash: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    version: int
    chunk_count: int
    embedding_model: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentChunkSchema(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    token_count: Optional[int] = None
    metadata_: Optional[Dict[str, Any]] = None
    vector_id: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IngestionJobBase(BaseModel):
    data_source_id: uuid.UUID


class IngestionJobCreate(IngestionJobBase):
    pass


class IngestionJob(IngestionJobBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    status: IngestionStatus
    total_documents: int
    processed_documents: int
    failed_documents: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IngestionTriggerRequest(BaseModel):
    data_source_id: uuid.UUID
    force_reindex: bool = False


class IngestionTriggerResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    message: str
