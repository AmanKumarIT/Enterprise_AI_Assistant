from fastapi import APIRouter

from app.api.v1 import auth, users, workspaces, sources, documents, feedback, chat

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
api_router.include_router(sources.router, prefix="/sources", tags=["data-sources"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
