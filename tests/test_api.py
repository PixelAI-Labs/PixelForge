"""Tests for API endpoints using a mock ModelManager (per Testing.md).

The mock replaces the real SD pipeline so tests run without GPU/model.
"""

import time
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
    mm._pipe = object()
    mm._device = object()
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


def _auth_header_for(user_id: str, username: str) -> dict:
    """Return an Authorization header for a specific synthetic test user."""
    token = create_access_token(user_id, username)
    return {"Authorization": f"Bearer {token}"}


def _wait_for_session_iteration(
    client: TestClient,
    session_id: str,
    headers: dict,
    timeout_s: float = 0.75,
) -> dict:
    """Poll until session iteration 0 exists (background task completion)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/sessions/{session_id}", headers=headers)
        if resp.status_code == 200:
            session = resp.json()
            if session.get("iterations"):
                return session
        time.sleep(0.01)
    raise AssertionError("Session did not produce an initial iteration in time")


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


class TestUserDataIsolation:
    def test_jobs_are_user_scoped(self, client: TestClient) -> None:
        user1 = _auth_header_for("user-1", "alice")
        user2 = _auth_header_for("user-2", "bob")

        resp1 = client.post("/generate", json={"prompt": "user 1 image"}, headers=user1)
        assert resp1.status_code == 200
        job1 = resp1.json()["job_id"]

        resp2 = client.post("/generate", json={"prompt": "user 2 image"}, headers=user2)
        assert resp2.status_code == 200
        job2 = resp2.json()["job_id"]

        jobs_user1 = client.get("/jobs", headers=user1)
        assert jobs_user1.status_code == 200
        ids_user1 = {j["job_id"] for j in jobs_user1.json()}
        assert job1 in ids_user1
        assert job2 not in ids_user1

        jobs_user2 = client.get("/jobs", headers=user2)
        assert jobs_user2.status_code == 200
        ids_user2 = {j["job_id"] for j in jobs_user2.json()}
        assert job2 in ids_user2
        assert job1 not in ids_user2

        assert client.get(f"/jobs/{job2}", headers=user1).status_code == 404
        assert client.get(f"/jobs/{job2}/image", headers=user1).status_code == 404

    def test_sessions_and_artifacts_are_user_scoped(self, client: TestClient) -> None:
        user1 = _auth_header_for("user-3", "charlie")
        user2 = _auth_header_for("user-4", "diana")

        create_resp = client.post(
            "/generate-session",
            json={"prompt": "session owner image"},
            headers=user1,
        )
        assert create_resp.status_code == 200
        session_id = create_resp.json()["session_id"]

        session = _wait_for_session_iteration(client, session_id, user1)

        sessions_user1 = client.get("/sessions", headers=user1)
        assert sessions_user1.status_code == 200
        ids_user1 = {s["session_id"] for s in sessions_user1.json()}
        assert session_id in ids_user1

        sessions_user2 = client.get("/sessions", headers=user2)
        assert sessions_user2.status_code == 200
        ids_user2 = {s["session_id"] for s in sessions_user2.json()}
        assert session_id not in ids_user2

        assert client.get(f"/sessions/{session_id}", headers=user2).status_code == 404
        assert (
            client.post(
                "/edit",
                json={
                    "session_id": session_id,
                    "edit_instruction": "change the lighting",
                    "strength": 0.35,
                },
                headers=user2,
            ).status_code
            == 404
        )
        assert client.get(f"/sessions/{session_id}/image/0", headers=user2).status_code == 404

        artifact_id = session["iterations"][0]["artifact_id"]
        assert artifact_id

        assert client.get(f"/artifacts/{artifact_id}", headers=user2).status_code == 404

        own_artifact = client.get(f"/artifacts/{artifact_id}", headers=user1)
        assert own_artifact.status_code == 200
        assert own_artifact.headers.get("content-type", "").startswith("image/png")
