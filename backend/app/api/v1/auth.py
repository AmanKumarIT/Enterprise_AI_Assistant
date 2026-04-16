from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.auth import security
from app.db.session import AsyncSessionLocal
from app.auth.deps import get_db
from app.models.user import User
from app.models.workspace import Workspace, UserWorkspace, WorkspaceRole
from app.models.document import DataSource, SourceType
from app.schemas.token import Token
from app.schemas.user import UserCreate, User as UserSchema

router = APIRouter()

@router.post("/login/access-token", response_model=Token)
async def login_access_token(
    db: AsyncSession = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()
) -> Token:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    stmt = select(User).where(User.email == form_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return Token(
        access_token=security.create_access_token(
            user.id, expires_delta=access_token_expires
        ),
        token_type="bearer",
    )

@router.post("/signup", response_model=UserSchema)
async def create_user_signup(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserCreate,
) -> User:
    """
    Create new user without the need to be logged in.
    """
    stmt = select(User).where(User.email == user_in.email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system",
        )
    user = User(
        email=user_in.email,
        hashed_password=security.get_password_hash(user_in.password),
        full_name=user_in.full_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Automatically create a default workspace for the new user
    workspace = Workspace(
        name="Default Workspace",
        description=f"{user_in.full_name}'s personal workspace"
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)

    # Add user as ADMIN to the workspace
    user_workspace = UserWorkspace(
        user_id=user.id,
        workspace_id=workspace.id,
        role=WorkspaceRole.ADMIN
    )
    db.add(user_workspace)

    # Create a default file source for uploads
    default_source = DataSource(
        workspace_id=workspace.id,
        name="My Files",
        source_type=SourceType.PDF,
        created_by=user.id,
        connection_config={}
    )
    db.add(default_source)

    await db.commit()
    
    return user
