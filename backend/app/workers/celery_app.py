"""
Celery application configuration and worker setup.
Uses Redis as broker and result backend.
"""
import logging
import sys
from celery import Celery
from app.core.config import settings
import ssl

logger = logging.getLogger(__name__)

celery_app = Celery(
    "eka_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

logger.info("Celery initialized with BROKER: %s", settings.REDIS_URL)
logger.info("Celery initialized with BACKEND: %s", settings.REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_default_queue="ingestion",
    task_queues={
        "ingestion": {"exchange": "ingestion", "routing_key": "ingestion"},
        "sync": {"exchange": "sync", "routing_key": "sync"},
    },
    task_routes={
        "app.workers.ingestion_tasks.run_ingestion_job": {"queue": "ingestion"},
        "app.workers.ingestion_tasks.run_scheduled_sync": {"queue": "sync"},
    },
    task_default_retry_delay=60,
    task_max_retries=3,
    broker_connection_retry_on_startup=True,
    # Use solo pool on Windows to avoid WinError 5 PermissionError
    worker_pool="solo" if sys.platform == "win32" else "prefork",
    
)

if settings.REDIS_URL.startswith("rediss://"):
    celery_app.conf.broker_use_ssl = {
        "ssl_cert_reqs": ssl.CERT_NONE
    }

    celery_app.conf.redis_backend_use_ssl = {
        "ssl_cert_reqs": ssl.CERT_NONE
    }

celery_app.autodiscover_tasks(["app.workers"])

# Explicitly import tasks to ensure they are registered even if autodiscover fails
try:
    import app.workers.ingestion_tasks
    logger.info("Successfully imported app.workers.ingestion_tasks")
except ImportError as e:
    logger.error("Failed to import app.workers.ingestion_tasks: %s", str(e))
