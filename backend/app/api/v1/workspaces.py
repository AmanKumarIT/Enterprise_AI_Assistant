from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth.deps import get_current_active_user, get_db
from app.models.user import User
from app.models.workspace import Workspace, UserWorkspace, WorkspaceRole
from app.models.document import DataSource, SourceType
from app.schemas.workspace import WorkspaceCreate, Workspace as WorkspaceSchema

router = APIRouter()

@router.post("/", response_model=WorkspaceSchema)
async def create_workspace(
    *,
    db: AsyncSession = Depends(get_db),
    workspace_in: WorkspaceCreate,
    current_user: User = Depends(get_current_active_user),
) -> Workspace:
    """
    Create new workspace.
    """
    workspace = Workspace(name=workspace_in.name, description=workspace_in.description)
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    
    # Automatically add creator as ADMIN
    user_workspace = UserWorkspace(
        user_id=current_user.id,
        workspace_id=workspace.id,
        role=WorkspaceRole.ADMIN
    )
    db.add(user_workspace)
    
    # Create a default file source for uploads
    default_source = DataSource(
        workspace_id=workspace.id,
        name="My Files",
        source_type=SourceType.PDF,
        created_by=current_user.id,
        connection_config={}
    )
    db.add(default_source)
    
    await db.commit()
    
    return workspace

@router.get("/", response_model=List[WorkspaceSchema])
async def read_user_workspaces(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[Workspace]:
    """
    Retrieve workspaces for current user.
    """
    stmt = select(Workspace).join(UserWorkspace).where(UserWorkspace.user_id == current_user.id)
    result = await db.execute(stmt)
    workspaces = result.scalars().all()
    return list(workspaces)
