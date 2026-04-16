import os
import uuid
import logging
import shutil
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth.deps import get_current_active_user, get_db
from app.models.user import User
from app.models.document import Document, DataSource, IngestionJob, IngestionStatus, SourceType
from app.schemas.document import Document as DocumentSchema
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

logger.info("FastAPI Document module loaded. Broker URL configured: %s", settings.REDIS_URL)

UPLOAD_DIR = Path("uploads")

def determine_source_type(filename: str) -> SourceType:
    """Determine SourceType enum from file extension."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return SourceType.PDF
    if lower.endswith(".docx"):
        return SourceType.DOCX
    return SourceType.TXT


@router.post("/upload")
async def upload_documents(
    workspace_id: uuid.UUID = Form(...),
    data_source_id: uuid.UUID = Form(...),
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Upload one or more files (PDF/DOCX/TXT) for ingestion.
    Creates documents and triggers background ingestion.
    """
    logger.info("Received upload request for workspace_id=%s, data_source_id=%s. Files count: %d", workspace_id, data_source_id, len(files))
    stmt = select(DataSource).where(DataSource.id == data_source_id)
    result = await db.execute(stmt)
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    # Ensure upload directory exists
    workspace_upload_dir = UPLOAD_DIR / str(workspace_id)
    workspace_upload_dir.mkdir(parents=True, exist_ok=True)

    filenames = []
    for file in files:
        unique_filename = f"{uuid.uuid4()}_{file.filename}"
        file_path = workspace_upload_dir / unique_filename
        
        # Save file to local storage
        try:
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
            logger.info("Saved file %s to %s", file.filename, file_path)
        except Exception as e:
            logger.exception("Failed to save uploaded file %s", file.filename)
            continue

        # Create Document record (pre-registered)
        doc = Document(
            data_source_id=ds.id,
            workspace_id=workspace_id,
            title=file.filename,
            source_uri=str(file_path),
            source_type=determine_source_type(file.filename),
            is_active=True,
        )
        db.add(doc)
        await db.flush()  # To get the doc.id
        logger.info("Created Document record: id=%s, title=%s", doc.id, doc.title)
        filenames.append(file.filename)

    job = IngestionJob(
        data_source_id=ds.id,
        workspace_id=workspace_id,
        status=IngestionStatus.PENDING,
        total_documents=len(filenames),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.info("Created IngestionJob record: id=%s for workspace_id=%s", job.id, workspace_id)

    try:
        from app.workers.ingestion_tasks import run_ingestion_job
        logger.info("Dispatching ingestion task: run_ingestion_job.delay(job_id=%s) to queue 'ingestion'", job.id)
        run_ingestion_job.delay(str(job.id))
    except Exception as e:
        logger.error("Failed to dispatch ingestion task: %s", str(e))

    return {
        "job_id": str(job.id),
        "files_received": len(filenames),
        "filenames": filenames,
        "status": "queued",
    }


@router.get("/", response_model=List[DocumentSchema])
async def list_documents(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: int = 0,
    limit: int = 100,
    source_type: str = None,
):
    """List documents for a workspace with optional source type filtering."""
    stmt = select(Document).where(
        Document.workspace_id == workspace_id,
        Document.is_active == True,
    )
    if source_type:
        stmt = stmt.where(Document.source_type == source_type)

    stmt = stmt.order_by(Document.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{document_id}", response_model=DocumentSchema)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a specific document by ID."""
    stmt = select(Document).where(Document.id == document_id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Delete a document and its vectors."""
    stmt = select(Document).where(Document.id == document_id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    from app.services.vector_store import vector_store_service
    try:
        vector_store_service.delete_by_document(doc.workspace_id, str(document_id))
    except Exception:
        pass

    # Clean up local file if it exists
    if doc.source_uri and os.path.exists(doc.source_uri):
        try:
            os.remove(doc.source_uri)
        except Exception as e:
            logger.warning("Failed to delete local file %s: %s", doc.source_uri, str(e))

    doc.is_active = False
    await db.commit()
    return {"status": "deleted", "document_id": str(document_id)}
