"""
Pipeline registry and factory.
Resolves the correct ingestion pipeline based on the data source type.
"""
from typing import Dict, Type
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DataSource, SourceType
from app.services.embedding import BaseEmbedder
from app.ingestion.base import BaseIngestionPipeline
from app.ingestion.file_pipeline import FileIngestionPipeline
from app.ingestion.github_pipeline import GitHubIngestionPipeline
from app.ingestion.sql_pipeline import SQLIngestionPipeline
from app.ingestion.slack_pipeline import SlackIngestionPipeline
from app.ingestion.confluence_notion_pipeline import (
    ConfluenceIngestionPipeline,
    NotionIngestionPipeline,
)
from app.ingestion.jira_pipeline import JiraIngestionPipeline


PIPELINE_REGISTRY: Dict[SourceType, Type[BaseIngestionPipeline]] = {
    SourceType.PDF: FileIngestionPipeline,
    SourceType.DOCX: FileIngestionPipeline,
    SourceType.TXT: FileIngestionPipeline,
    SourceType.GITHUB: GitHubIngestionPipeline,
    SourceType.SQL_DATABASE: SQLIngestionPipeline,
    SourceType.SLACK: SlackIngestionPipeline,
    SourceType.CONFLUENCE: ConfluenceIngestionPipeline,
    SourceType.NOTION: NotionIngestionPipeline,
    SourceType.JIRA: JiraIngestionPipeline,
}


def get_pipeline(
    source_type: SourceType,
    db: AsyncSession,
    embedder: BaseEmbedder,
    workspace_id: uuid.UUID,
    data_source: DataSource,
    **kwargs,
) -> BaseIngestionPipeline:
    """Create and return the appropriate ingestion pipeline for the given source type."""
    pipeline_class = PIPELINE_REGISTRY.get(source_type)
    if not pipeline_class:
        raise ValueError(f"No pipeline registered for source type: {source_type}")

    return pipeline_class(
        db=db,
        embedder=embedder,
        workspace_id=workspace_id,
        data_source=data_source,
        **kwargs,
    )
