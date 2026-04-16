from typing import Optional
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.models.feedback import FeedbackRating


class FeedbackCreate(BaseModel):
    query: str
    answer: str
    rating: FeedbackRating
    correction: Optional[str] = None
    session_id: Optional[str] = None


class FeedbackRead(FeedbackCreate):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FeedbackStats(BaseModel):
    total: int
    helpful: int
    not_helpful: int
    helpful_percentage: float
    with_corrections: int
