"""
Tests for authentication endpoints.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAuth:
    async def test_signup(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "newuser@test.com",
                "password": "StrongP@ss1",
                "full_name": "New User",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newuser@test.com"
        assert data["full_name"] == "New User"
        assert "id" in data

    async def test_signup_duplicate_email(self, client: AsyncClient):
        # First signup
        await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "dup@test.com",
                "password": "StrongP@ss1",
                "full_name": "Dup User",
            },
        )
        # Duplicate
        response = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "dup@test.com",
                "password": "StrongP@ss1",
                "full_name": "Dup User",
            },
        )
        assert response.status_code == 400

    async def test_login_success(self, client: AsyncClient):
        # Create user first
        await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "logintest@test.com",
                "password": "StrongP@ss1",
                "full_name": "Login User",
            },
        )
        response = await client.post(
            "/api/v1/auth/login/access-token",
            data={"username": "logintest@test.com", "password": "StrongP@ss1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient):
        # Create user
        await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "wrongpass@test.com",
                "password": "Correct1",
                "full_name": "User",
            },
        )
        response = await client.post(
            "/api/v1/auth/login/access-token",
            data={"username": "wrongpass@test.com", "password": "WrongPass"},
        )
        assert response.status_code == 400

    async def test_get_me(self, client: AsyncClient, auth_headers):
        response = await client.get("/api/v1/users/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "testuser@example.com"

    async def test_get_me_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/v1/users/me")
        assert response.status_code in (401, 403)
