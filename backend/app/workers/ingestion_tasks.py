"""
Celery tasks for background ingestion and scheduled sync jobs.
Handles orchestration, job tracking, retry logic, and error reporting.
"""
import logging
import uuid
import asyncio
from datetime import datetime, timezone

from celery import Task
from sqlalchemy.future import select

from app.workers.celery_app import celery_app
from app.db.session import AsyncSessionLocal
from app.models.document import DataSource, IngestionJob, IngestionStatus
from app.services.embedding import get_embedder
from app.ingestion.registry import get_pipeline

logger = logging.getLogger(__name__)


class IngestionTask(Task):
    """Custom task base with error handling and retry awareness."""
    autoretry_for = (Exception,)
    max_retries = 3
    default_retry_delay = 60


# def _run_async(coro):
#     """Run an async function in a new event loop for Celery compatibility."""
#     loop = asyncio.new_event_loop()
#     try:
#         return loop.run_until_complete(coro)
#     finally:
#         loop.close()

def _run_async(coro):
    return asyncio.run(coro)


@celery_app.task(base=IngestionTask, bind=True, name="app.workers.ingestion_tasks.run_ingestion_job")
def run_ingestion_job(self, job_id: str, force_reindex: bool = False):
    """
    Execute a single ingestion job. Called when a user triggers
    ingestion from the API or when a scheduled sync fires.
    """
    logger.info("TASK RECEIVED: run_ingestion_job(job_id=%s)", job_id)
    logger.info("Worker Version Check: Active at %s", datetime.now(timezone.utc).isoformat())
    
    logger.info("Celery task started: run_ingestion_job for job_id=%s, force_reindex=%s", job_id, force_reindex)
    _run_async(_execute_ingestion(job_id, force_reindex))
    logger.info("Celery task completed: run_ingestion_job for job_id=%s", job_id)


async def _execute_ingestion(job_id: str, force_reindex: bool = False):
    async with AsyncSessionLocal() as db:
        stmt = select(IngestionJob).where(IngestionJob.id == uuid.UUID(job_id))
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()

        if not job:
            logger.error("Ingestion job not found: %s", job_id)
            return
        
        logger.info("Fetched job details: id=%s, workspace_id=%s, data_source_id=%s", job.id, job.workspace_id, job.data_source_id)

        ds_stmt = select(DataSource).where(DataSource.id == job.data_source_id)
        ds_result = await db.execute(ds_stmt)
        data_source = ds_result.scalar_one_or_none()

        if not data_source:
            logger.error("Data source not found for job %s: data_source_id=%s", job_id, job.data_source_id)
            job.status = IngestionStatus.FAILED
            job.error_message = "Data source not found"
            await db.commit()
            return
        
        logger.info("Fetched data source details: id=%s, type=%s, name=%s", data_source.id, data_source.source_type, data_source.name)

        from app.services.embedding import get_active_embedder
        embedder = get_active_embedder()

        pipeline = get_pipeline(
            source_type=data_source.source_type,
            db=db,
            embedder=embedder,
            workspace_id=job.workspace_id,
            data_source=data_source,
        )
        logger.info("Selected pipeline class: %s for source_type=%s", pipeline.__class__.__name__, data_source.source_type)

        await pipeline.run(job, force_reindex=force_reindex)

        data_source.last_sync_at = datetime.now(timezone.utc)
        await db.commit()


@celery_app.task(name="app.workers.ingestion_tasks.run_scheduled_sync")
def run_scheduled_sync():
    """
    Periodic task that checks for data sources needing sync
    and queues ingestion jobs for each.
    """
    logger.info("Running scheduled sync check")
    _run_async(_check_and_queue_syncs())


async def _check_and_queue_syncs():
    async with AsyncSessionLocal() as db:
        stmt = select(DataSource).where(
            DataSource.is_active == True,
            DataSource.sync_frequency_minutes.isnot(None),
        )
        result = await db.execute(stmt)
        sources = result.scalars().all()

        now = datetime.now(timezone.utc)
        for source in sources:
            should_sync = False
            if source.last_sync_at is None:
                should_sync = True
            elif source.sync_frequency_minutes:
                elapsed = (now - source.last_sync_at).total_seconds() / 60
                should_sync = elapsed >= source.sync_frequency_minutes

            if should_sync:
                job = IngestionJob(
                    data_source_id=source.id,
                    workspace_id=source.workspace_id,
                    status=IngestionStatus.PENDING,
                )
                db.add(job)
                await db.flush()

                run_ingestion_job.delay(str(job.id))
                logger.info(
                    "Queued sync job %s for data source %s", job.id, source.name
                )

        await db.commit()
