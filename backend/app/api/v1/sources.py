"""
API endpoints for data source management and ingestion triggering.
"""
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth.deps import get_current_active_user, get_db
from app.models.user import User
from app.models.document import DataSource, IngestionJob, IngestionStatus, SourceType
from app.schemas.document import (
    DataSourceCreate,
    DataSourceUpdate,
    DataSource as DataSourceSchema,
    IngestionJob as IngestionJobSchema,
    IngestionTriggerRequest,
    IngestionTriggerResponse,
)
from app.workers.ingestion_tasks import run_ingestion_job

router = APIRouter()


@router.post("/", response_model=DataSourceSchema)
async def create_data_source(
    *,
    db: AsyncSession = Depends(get_db),
    source_in: DataSourceCreate,
    current_user: User = Depends(get_current_active_user),
    workspace_id: uuid.UUID,
) -> DataSource:
    """Create a new data source configuration."""
    data_source = DataSource(
        workspace_id=workspace_id,
        name=source_in.name,
        source_type=source_in.source_type,
        connection_config=source_in.connection_config,
        is_active=source_in.is_active,
        sync_frequency_minutes=source_in.sync_frequency_minutes,
        created_by=current_user.id,
    )
    db.add(data_source)
    await db.commit()
    await db.refresh(data_source)
    return data_source


@router.get("/", response_model=List[DataSourceSchema])
async def list_data_sources(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[DataSource]:
    """List all data sources for a workspace."""
    stmt = select(DataSource).where(DataSource.workspace_id == workspace_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{source_id}", response_model=DataSourceSchema)
async def get_data_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DataSource:
    """Get a specific data source."""
    stmt = select(DataSource).where(DataSource.id == source_id)
    result = await db.execute(stmt)
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")
    return ds


@router.put("/{source_id}", response_model=DataSourceSchema)
async def update_data_source(
    source_id: uuid.UUID,
    source_in: DataSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DataSource:
    """Update data source configuration."""
    stmt = select(DataSource).where(DataSource.id == source_id)
    result = await db.execute(stmt)
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    update_data = source_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(ds, field, value)

    await db.commit()
    await db.refresh(ds)
    return ds


@router.delete("/{source_id}")
async def delete_data_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Delete a data source and its associated documents/vectors."""
    stmt = select(DataSource).where(DataSource.id == source_id)
    result = await db.execute(stmt)
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    from app.services.vector_store import vector_store_service
    try:
        vector_store_service.delete_by_data_source(ds.workspace_id, str(source_id))
    except Exception:
        pass

    await db.delete(ds)
    await db.commit()
    return {"status": "deleted"}


@router.post("/ingest", response_model=IngestionTriggerResponse)
async def trigger_ingestion(
    *,
    db: AsyncSession = Depends(get_db),
    request: IngestionTriggerRequest,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
) -> IngestionTriggerResponse:
    """Trigger an ingestion job for a data source."""
    stmt = select(DataSource).where(DataSource.id == request.data_source_id)
    result = await db.execute(stmt)
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    job = IngestionJob(
        data_source_id=ds.id,
        workspace_id=workspace_id,
        status=IngestionStatus.PENDING,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    run_ingestion_job.delay(str(job.id), request.force_reindex)

    return IngestionTriggerResponse(
        job_id=job.id,
        status="queued",
        message=f"Ingestion job queued for data source '{ds.name}'",
    )


@router.get("/jobs/{workspace_id}", response_model=List[IngestionJobSchema])
async def list_ingestion_jobs(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: int = 0,
    limit: int = 50,
) -> List[IngestionJob]:
    """List ingestion jobs for a workspace."""
    stmt = (
        select(IngestionJob)
        .where(IngestionJob.workspace_id == workspace_id)
        .order_by(IngestionJob.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/jobs/{job_id}/status", response_model=IngestionJobSchema)
async def get_ingestion_job_status(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> IngestionJob:
    """Get the status of a specific ingestion job."""
    stmt = select(IngestionJob).where(IngestionJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return job
