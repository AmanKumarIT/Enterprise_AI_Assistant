"""
API endpoints for user feedback on AI-generated answers.
"""
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func as sql_func

from app.auth.deps import get_current_active_user, get_db
from app.models.user import User
from app.models.feedback import Feedback, FeedbackRating
from app.schemas.feedback import FeedbackCreate, FeedbackRead, FeedbackStats

router = APIRouter()


@router.post("/", response_model=FeedbackRead)
async def submit_feedback(
    *,
    db: AsyncSession = Depends(get_db),
    feedback_in: FeedbackCreate,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
) -> Feedback:
    """Submit feedback (helpful/not helpful) on an AI answer."""
    feedback = Feedback(
        workspace_id=workspace_id,
        user_id=current_user.id,
        query=feedback_in.query,
        answer=feedback_in.answer,
        rating=feedback_in.rating,
        correction=feedback_in.correction,
        session_id=feedback_in.session_id,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return feedback


@router.get("/", response_model=List[FeedbackRead])
async def list_feedback(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: int = 0,
    limit: int = 50,
    rating: str = None,
) -> List[Feedback]:
    """List feedback for a workspace with optional rating filter."""
    stmt = select(Feedback).where(Feedback.workspace_id == workspace_id)
    if rating:
        stmt = stmt.where(Feedback.rating == rating)
    stmt = stmt.order_by(Feedback.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/stats", response_model=FeedbackStats)
async def feedback_stats(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> FeedbackStats:
    """Get feedback analytics for a workspace."""
    base = select(Feedback).where(Feedback.workspace_id == workspace_id)

    total_result = await db.execute(
        select(sql_func.count()).select_from(base.subquery())
    )
    total = total_result.scalar() or 0

    helpful_result = await db.execute(
        select(sql_func.count()).select_from(
            base.where(Feedback.rating == FeedbackRating.HELPFUL).subquery()
        )
    )
    helpful = helpful_result.scalar() or 0

    not_helpful = total - helpful

    corrections_result = await db.execute(
        select(sql_func.count()).select_from(
            base.where(Feedback.correction.isnot(None)).subquery()
        )
    )
    with_corrections = corrections_result.scalar() or 0

    return FeedbackStats(
        total=total,
        helpful=helpful,
        not_helpful=not_helpful,
        helpful_percentage=round((helpful / total * 100) if total > 0 else 0, 2),
        with_corrections=with_corrections,
    )
