from typing import TYPE_CHECKING
import uuid
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.db.base_class import Base

if TYPE_CHECKING:
    from .user import User  # noqa: F401

class WorkspaceRole(str, enum.Enum):
    ADMIN = "ADMIN"
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"

class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    members: Mapped[list["UserWorkspace"]] = relationship("UserWorkspace", back_populates="workspace", cascade="all, delete-orphan")

class UserWorkspace(Base):
    __tablename__ = "user_workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[WorkspaceRole] = mapped_column(Enum(WorkspaceRole), default=WorkspaceRole.VIEWER, nullable=False)
    joined_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), 
        default=func.now(),
        server_default=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="workspaces")
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="members")
