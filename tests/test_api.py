"""Tests for API endpoints using a mock ModelManager (per Testing.md).

The mock replaces the real SD pipeline so tests run without GPU/model.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.app import create_app
from auth.security import create_access_token
from engines.model_manager import ModelManager
from engines.quality_evaluator import QualityEvaluator


# ---- helpers / fixtures ----------------------------------------

def _mock_model_manager() -> ModelManager:
    """ModelManager whose generate() returns a dummy image."""
    mm = MagicMock(spec=ModelManager)
    mm.is_loaded = True
    mm.generate.return_value = Image.new("RGB", (64, 64), color="blue")
    return mm


def _mock_quality_evaluator() -> QualityEvaluator:
    """QualityEvaluator that always returns a high score."""
    qe = MagicMock(spec=QualityEvaluator)
    qe.evaluate.return_value = 0.85
    return qe


def _auth_header() -> dict:
    """Return an Authorization header with a valid JWT."""
    token = create_access_token("test-user-id", "testuser")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client() -> TestClient:
    app = create_app(
        model_manager=_mock_model_manager(),
        quality_evaluator=_mock_quality_evaluator(),
        use_memory=True,
    )
    return TestClient(app)


# ---- tests -----------------------------------------------------

class TestGenerateEndpoint:
    def test_generate_returns_job_id(self, client: TestClient) -> None:
        resp = client.post("/generate", json={"prompt": "a dog"}, headers=_auth_header())
        assert resp.status_code == 200
        body = resp.json()
        assert "job_id" in body
        assert isinstance(body["job_id"], str)

    def test_generate_requires_auth(self, client: TestClient) -> None:
        resp = client.post("/generate", json={"prompt": "a dog"})
        assert resp.status_code in (401, 403)


class TestAuthEndpoints:
    def test_register_and_login(self, client: TestClient) -> None:
        # Register
        resp = client.post("/auth/register", json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "password123",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert body["username"] == "testuser"

        # Login
        resp = client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "password123",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body

    def test_me_endpoint(self, client: TestClient) -> None:
        # Register first
        resp = client.post("/auth/register", json={
            "username": "meuser",
            "email": "me@example.com",
            "password": "password123",
        })
        token = resp.json()["access_token"]

        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["username"] == "meuser"
