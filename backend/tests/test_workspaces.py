"""
Tests for workspace endpoints.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestWorkspaces:
    async def test_create_workspace(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/workspaces/",
            json={"name": "Test WS", "description": "A test workspace"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test WS"
        assert "id" in data

    async def test_list_workspaces(self, client: AsyncClient, auth_headers):
        # Create a workspace
        await client.post(
            "/api/v1/workspaces/",
            json={"name": "List WS"},
            headers=auth_headers,
        )
        response = await client.get("/api/v1/workspaces/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_list_workspaces_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/v1/workspaces/")
        assert response.status_code in (401, 403)
