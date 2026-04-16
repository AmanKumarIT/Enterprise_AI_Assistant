"""
Jira ingestion pipeline.
Syncs issues, comments, attachments, status history, and custom fields
from Jira Cloud or Server.
"""
import logging
import re
from typing import List, Optional, Dict, Any

from app.ingestion.base import BaseIngestionPipeline, RawDocument
from app.services.chunking import TextChunker

logger = logging.getLogger(__name__)

MAX_ISSUES = 5000


class JiraIngestionPipeline(BaseIngestionPipeline):
    """
    Syncs Jira tickets including comments, status history, and key fields.

    Expected connection_config:
    {
        "base_url": "https://yourco.atlassian.net",
        "username": "user@company.com",
        "api_token": "...",
        "project_keys": ["PROJ", "ENG"],  (optional)
        "jql": "project = ENG AND updated >= -30d",  (optional)
        "max_issues": 2000,  (optional)
    }
    """

    def get_chunker(self):
        return TextChunker(chunk_size=1000, chunk_overlap=150)

    async def extract_documents(self) -> List[RawDocument]:
        import requests

        config = self.data_source.connection_config or {}
        base_url: str = config.get("base_url", "").rstrip("/")
        username: str = config.get("username", "")
        api_token: str = config.get("api_token", "")
        project_keys: Optional[List[str]] = config.get("project_keys")
        jql: Optional[str] = config.get("jql")
        max_issues: int = config.get("max_issues", MAX_ISSUES)

        if not all([base_url, username, api_token]):
            raise ValueError("Missing base_url, username, or api_token in connection_config")

        session = requests.Session()
        session.auth = (username, api_token)
        session.headers.update({"Accept": "application/json"})

        if not jql:
            if project_keys:
                project_clause = " OR ".join(f"project = {k}" for k in project_keys)
                jql = f"({project_clause}) ORDER BY updated DESC"
            else:
                jql = "ORDER BY updated DESC"

        raw_docs: List[RawDocument] = []
        start_at = 0
        batch_size = 50

        while start_at < max_issues:
            url = (
                f"{base_url}/rest/api/3/search"
                f"?jql={requests.utils.quote(jql)}"
                f"&startAt={start_at}&maxResults={batch_size}"
                f"&fields=summary,description,status,priority,assignee,"
                f"issuetype,labels,components,created,updated,comment,"
                f"resolution,reporter,fixVersions"
                f"&expand=changelog"
            )
            response = session.get(url)
            response.raise_for_status()
            data = response.json()

            issues = data.get("issues", [])
            if not issues:
                break

            for issue in issues:
                doc = self._process_issue(issue, base_url)
                if doc:
                    raw_docs.append(doc)

            start_at += len(issues)
            total = data.get("total", 0)
            if start_at >= total:
                break

        logger.info("Extracted %d Jira issues", len(raw_docs))
        return raw_docs

    def _process_issue(self, issue: Dict[str, Any], base_url: str) -> Optional[RawDocument]:
        key = issue.get("key", "")
        fields = issue.get("fields", {})

        summary = fields.get("summary", "")
        description_raw = fields.get("description")
        description = self._adf_to_text(description_raw) if description_raw else ""

        status = fields.get("status", {}).get("name", "")
        priority = fields.get("priority", {}).get("name", "")
        issue_type = fields.get("issuetype", {}).get("name", "")
        assignee = fields.get("assignee", {})
        assignee_name = assignee.get("displayName", "Unassigned") if assignee else "Unassigned"
        reporter = fields.get("reporter", {})
        reporter_name = reporter.get("displayName", "Unknown") if reporter else "Unknown"
        labels = fields.get("labels", [])
        components = [c.get("name", "") for c in fields.get("components", [])]
        resolution = fields.get("resolution")
        resolution_name = resolution.get("name", "") if resolution else "Unresolved"
        created = fields.get("created", "")
        updated = fields.get("updated", "")

        comments_data = fields.get("comment", {}).get("comments", [])
        comment_texts: List[str] = []
        for comment in comments_data:
            author = comment.get("author", {}).get("displayName", "unknown")
            body = self._adf_to_text(comment.get("body")) if comment.get("body") else ""
            created_at = comment.get("created", "")[:10]
            if body.strip():
                comment_texts.append(f"[{created_at}] {author}: {body}")

        changelog = issue.get("changelog", {}).get("histories", [])
        status_changes: List[str] = []
        for history in changelog:
            for item in history.get("items", []):
                if item.get("field") == "status":
                    change_date = history.get("created", "")[:10]
                    from_status = item.get("fromString", "")
                    to_status = item.get("toString", "")
                    status_changes.append(f"{change_date}: {from_status} → {to_status}")

        content_parts = [
            f"Issue: {key}",
            f"Type: {issue_type}",
            f"Summary: {summary}",
            f"Status: {status}",
            f"Priority: {priority}",
            f"Assignee: {assignee_name}",
            f"Reporter: {reporter_name}",
            f"Resolution: {resolution_name}",
            f"Labels: {', '.join(labels)}",
            f"Components: {', '.join(components)}",
            f"Created: {created[:10] if created else ''}",
            f"Updated: {updated[:10] if updated else ''}",
        ]

        if description:
            content_parts.append(f"\nDescription:\n{description}")

        if comment_texts:
            content_parts.append(f"\nComments ({len(comment_texts)}):")
            content_parts.extend(comment_texts)

        if status_changes:
            content_parts.append(f"\nStatus History:")
            content_parts.extend(status_changes)

        content = "\n".join(content_parts)

        return RawDocument(
            title=f"{key}: {summary}",
            content=content,
            source_uri=f"{base_url}/browse/{key}",
            metadata={
                "issue_key": key,
                "issue_type": issue_type,
                "status": status,
                "priority": priority,
                "assignee": assignee_name,
                "reporter": reporter_name,
                "labels": labels,
                "components": components,
                "resolution": resolution_name,
                "comment_count": len(comment_texts),
                "created": created,
                "updated": updated,
            },
        )

    def _adf_to_text(self, adf_node: Any) -> str:
        """Convert Atlassian Document Format (ADF) JSON to plain text."""
        if isinstance(adf_node, str):
            return adf_node
        if not isinstance(adf_node, dict):
            return ""

        node_type = adf_node.get("type", "")
        text_parts: List[str] = []

        if node_type == "text":
            return adf_node.get("text", "")

        content = adf_node.get("content", [])
        for child in content:
            text_parts.append(self._adf_to_text(child))

        joined = "".join(text_parts)

        if node_type in ("paragraph", "heading"):
            return joined + "\n"
        if node_type == "listItem":
            return f"• {joined}\n"
        if node_type == "codeBlock":
            return f"\n```\n{joined}\n```\n"

        return joined
