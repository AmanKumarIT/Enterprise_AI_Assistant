"""
Pydantic schemas for the chat/query interface.
"""
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ChatRequest(BaseModel):
    """User's chat query request."""
    query: str
    workspace_id: uuid.UUID
    source_type_filter: Optional[str] = None
    data_source_id: Optional[uuid.UUID] = None
    use_agent: bool = False
    session_id: Optional[str] = None


class CitationResponse(BaseModel):
    """A single citation in the response."""
    source_index: int
    source_type: str
    document_title: str
    source_uri: str
    chunk_index: Optional[int] = None
    retrieval_score: float = 0.0
    rerank_score: float = 0.0


class ChatResponse(BaseModel):
    """Full response from the RAG pipeline."""
    answer: str
    citations: List[CitationResponse] = []
    confidence_score: float = 0.0
    query_intent: str = ""
    target_sources: List[str] = []
    retrieval_metadata: Dict[str, Any] = {}
    processing_time_ms: float = 0.0
    session_id: Optional[str] = None


class ChatHistoryItem(BaseModel):
    """A single item in chat history."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime
    citations: List[CitationResponse] = []
    confidence_score: Optional[float] = None


class ChatSession(BaseModel):
    """A chat session with history."""
    session_id: str
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    history: List[ChatHistoryItem] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
