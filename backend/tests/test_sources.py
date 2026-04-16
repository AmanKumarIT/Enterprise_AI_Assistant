"""
Tests for data source and ingestion endpoints.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestSources:
    async def test_create_source(self, client: AsyncClient, auth_headers, test_workspace):
        response = await client.post(
            f"/api/v1/sources/?workspace_id={test_workspace.id}",
            json={
                "name": "Test PDF Source",
                "source_type": "PDF",
                "connection_config": {},
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test PDF Source"
        assert data["source_type"] == "PDF"

    async def test_list_sources(self, client: AsyncClient, auth_headers, test_workspace):
        # Create source first
        await client.post(
            f"/api/v1/sources/?workspace_id={test_workspace.id}",
            json={"name": "List Source", "source_type": "GITHUB"},
            headers=auth_headers,
        )
        response = await client.get(
            f"/api/v1/sources/?workspace_id={test_workspace.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_delete_source(self, client: AsyncClient, auth_headers, test_workspace):
        # Create
        create_resp = await client.post(
            f"/api/v1/sources/?workspace_id={test_workspace.id}",
            json={"name": "Delete Me", "source_type": "TXT"},
            headers=auth_headers,
        )
        source_id = create_resp.json()["id"]
        # Delete
        delete_resp = await client.delete(
            f"/api/v1/sources/{source_id}",
            headers=auth_headers,
        )
        assert delete_resp.status_code == 200


@pytest.mark.asyncio
class TestFeedback:
    async def test_submit_feedback(self, client: AsyncClient, auth_headers, test_workspace):
        response = await client.post(
            f"/api/v1/feedback/?workspace_id={test_workspace.id}",
            json={
                "query": "What are sales?",
                "answer": "Sales are transactions.",
                "rating": "HELPFUL",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == "HELPFUL"

    async def test_get_feedback_stats(self, client: AsyncClient, auth_headers, test_workspace):
        response = await client.get(
            f"/api/v1/feedback/stats?workspace_id={test_workspace.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
