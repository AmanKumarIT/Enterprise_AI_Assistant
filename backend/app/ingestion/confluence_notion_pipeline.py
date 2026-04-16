"""
Confluence and Notion ingestion pipeline.
Syncs pages via their respective APIs with rich text parsing
and hierarchical page structure support.
"""
import logging
import re
from typing import List, Optional, Dict, Any

from app.ingestion.base import BaseIngestionPipeline, RawDocument
from app.services.chunking import TextChunker

logger = logging.getLogger(__name__)


class ConfluenceIngestionPipeline(BaseIngestionPipeline):
    """
    Syncs pages from Atlassian Confluence.

    Expected connection_config:
    {
        "base_url": "https://yourco.atlassian.net/wiki",
        "username": "user@company.com",
        "api_token": "...",
        "space_keys": ["ENG", "PRODUCT"],  (optional)
        "page_limit": 500,  (optional)
    }
    """

    def get_chunker(self):
        return TextChunker(chunk_size=1000, chunk_overlap=200)

    async def extract_documents(self) -> List[RawDocument]:
        import requests

        config = self.data_source.connection_config or {}
        base_url: str = config.get("base_url", "").rstrip("/")
        username: str = config.get("username", "")
        api_token: str = config.get("api_token", "")
        space_keys: Optional[List[str]] = config.get("space_keys")
        page_limit: int = config.get("page_limit", 500)

        if not all([base_url, username, api_token]):
            raise ValueError("Missing base_url, username, or api_token in connection_config")

        session = requests.Session()
        session.auth = (username, api_token)
        session.headers.update({"Accept": "application/json"})

        raw_docs: List[RawDocument] = []
        spaces = space_keys or self._get_all_spaces(session, base_url)

        for space_key in spaces:
            start = 0
            fetched = 0

            while fetched < page_limit:
                url = (
                    f"{base_url}/rest/api/content"
                    f"?spaceKey={space_key}&type=page"
                    f"&expand=body.storage,ancestors,version"
                    f"&start={start}&limit=50"
                )
                response = session.get(url)
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])

                if not results:
                    break

                for page in results:
                    page_id = page["id"]
                    title = page.get("title", f"Page {page_id}")
                    html_body = page.get("body", {}).get("storage", {}).get("value", "")
                    plain_text = self._html_to_text(html_body)

                    if not plain_text.strip():
                        continue

                    ancestors = page.get("ancestors", [])
                    breadcrumb = " > ".join(a.get("title", "") for a in ancestors)
                    version_num = page.get("version", {}).get("number", 1)

                    raw_docs.append(
                        RawDocument(
                            title=title,
                            content=f"Breadcrumb: {breadcrumb}\nTitle: {title}\n\n{plain_text}",
                            source_uri=f"{base_url}/pages/{page_id}",
                            metadata={
                                "space_key": space_key,
                                "page_id": page_id,
                                "breadcrumb": breadcrumb,
                                "version": version_num,
                                "ancestor_count": len(ancestors),
                            },
                        )
                    )
                    fetched += 1

                start += len(results)
                if data.get("size", 0) < 50:
                    break

            logger.info("Extracted %d pages from Confluence space %s", fetched, space_key)

        return raw_docs

    def _get_all_spaces(self, session, base_url: str) -> List[str]:
        url = f"{base_url}/rest/api/space?limit=100"
        response = session.get(url)
        response.raise_for_status()
        spaces = response.json().get("results", [])
        return [s["key"] for s in spaces]

    def _html_to_text(self, html: str) -> str:
        text = re.sub(r"<br\s*/?>", "\n", html)
        text = re.sub(r"</(p|div|h[1-6]|li|tr)>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


class NotionIngestionPipeline(BaseIngestionPipeline):
    """
    Syncs pages from Notion via the Notion API.

    Expected connection_config:
    {
        "api_key": "secret_...",
        "database_ids": ["..."],  (optional - searches all if omitted)
        "page_limit": 500,  (optional)
    }
    """

    def get_chunker(self):
        return TextChunker(chunk_size=1000, chunk_overlap=200)

    async def extract_documents(self) -> List[RawDocument]:
        import requests

        config = self.data_source.connection_config or {}
        api_key: str = config.get("api_key", "")
        database_ids: Optional[List[str]] = config.get("database_ids")
        page_limit: int = config.get("page_limit", 500)

        if not api_key:
            raise ValueError("Missing api_key in connection_config")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        raw_docs: List[RawDocument] = []

        if database_ids:
            for db_id in database_ids:
                pages = self._query_database(headers, db_id, page_limit)
                raw_docs.extend(pages)
        else:
            pages = self._search_all_pages(headers, page_limit)
            raw_docs.extend(pages)

        logger.info("Total Notion documents extracted: %d", len(raw_docs))
        return raw_docs

    def _search_all_pages(self, headers: Dict, limit: int) -> List[RawDocument]:
        import requests

        raw_docs: List[RawDocument] = []
        url = "https://api.notion.com/v1/search"
        has_more = True
        start_cursor = None
        fetched = 0

        while has_more and fetched < limit:
            body: Dict[str, Any] = {
                "filter": {"property": "object", "value": "page"},
                "page_size": 100,
            }
            if start_cursor:
                body["start_cursor"] = start_cursor

            response = requests.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()

            for page in data.get("results", []):
                doc = self._process_page(headers, page)
                if doc:
                    raw_docs.append(doc)
                    fetched += 1

            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        return raw_docs

    def _query_database(self, headers: Dict, db_id: str, limit: int) -> List[RawDocument]:
        import requests

        raw_docs: List[RawDocument] = []
        url = f"https://api.notion.com/v1/databases/{db_id}/query"
        has_more = True
        start_cursor = None
        fetched = 0

        while has_more and fetched < limit:
            body: Dict[str, Any] = {"page_size": 100}
            if start_cursor:
                body["start_cursor"] = start_cursor

            response = requests.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()

            for page in data.get("results", []):
                doc = self._process_page(headers, page)
                if doc:
                    raw_docs.append(doc)
                    fetched += 1

            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        return raw_docs

    def _process_page(self, headers: Dict, page: Dict) -> Optional[RawDocument]:
        import requests

        page_id = page["id"]
        title = self._extract_title(page)

        blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
        blocks_response = requests.get(blocks_url, headers=headers)
        if blocks_response.status_code != 200:
            return None

        blocks = blocks_response.json().get("results", [])
        text_parts = [self._block_to_text(b) for b in blocks]
        content = "\n\n".join(part for part in text_parts if part)

        if not content.strip():
            return None

        parent_type = page.get("parent", {}).get("type", "")
        return RawDocument(
            title=title,
            content=f"Title: {title}\n\n{content}",
            source_uri=page.get("url", f"notion://{page_id}"),
            metadata={
                "page_id": page_id,
                "parent_type": parent_type,
                "created_time": page.get("created_time", ""),
                "last_edited_time": page.get("last_edited_time", ""),
            },
        )

    def _extract_title(self, page: Dict) -> str:
        properties = page.get("properties", {})
        for prop in properties.values():
            if prop.get("type") == "title":
                title_parts = prop.get("title", [])
                return "".join(t.get("plain_text", "") for t in title_parts) or "Untitled"
        return "Untitled"

    def _block_to_text(self, block: Dict) -> str:
        block_type = block.get("type", "")
        data = block.get(block_type, {})

        if block_type in (
            "paragraph", "heading_1", "heading_2", "heading_3",
            "bulleted_list_item", "numbered_list_item", "quote", "callout",
        ):
            rich_texts = data.get("rich_text", [])
            text = "".join(rt.get("plain_text", "") for rt in rich_texts)
            if block_type.startswith("heading"):
                level = block_type[-1]
                return f"{'#' * int(level)} {text}"
            if block_type in ("bulleted_list_item", "numbered_list_item"):
                return f"• {text}"
            return text

        if block_type == "code":
            rich_texts = data.get("rich_text", [])
            code = "".join(rt.get("plain_text", "") for rt in rich_texts)
            lang = data.get("language", "")
            return f"```{lang}\n{code}\n```"

        if block_type == "toggle":
            rich_texts = data.get("rich_text", [])
            return "".join(rt.get("plain_text", "") for rt in rich_texts)

        return ""
