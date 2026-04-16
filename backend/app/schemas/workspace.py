from typing import Optional, List
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.workspace import WorkspaceRole
from app.schemas.user import User

class WorkspaceBase(BaseModel):
    name: str
    description: Optional[str] = None

class WorkspaceCreate(WorkspaceBase):
    pass

class WorkspaceUpdate(WorkspaceBase):
    name: Optional[str] = None

class WorkspaceInDBBase(WorkspaceBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class Workspace(WorkspaceInDBBase):
    pass

class UserWorkspaceInfo(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    role: WorkspaceRole
    joined_at: datetime
    workspace: Workspace

    model_config = ConfigDict(from_attributes=True)
