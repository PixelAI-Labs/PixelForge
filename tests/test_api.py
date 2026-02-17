"""Tests for API endpoints using a mock ModelManager (per Testing.md).

The mock replaces the real SD pipeline so tests run without GPU/model.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.app import create_app
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


@pytest.fixture
def client() -> TestClient:
    app = create_app(
        model_manager=_mock_model_manager(),
        quality_evaluator=_mock_quality_evaluator(),
    )
    return TestClient(app)


# ---- tests -----------------------------------------------------

class TestGenerateEndpoint:
    def test_generate_returns_job_id(self, client: TestClient) -> None:
        resp = client.post("/generate", json={"prompt": "a dog"})
        assert resp.status_code == 200
        body = resp.json()
        assert "job_id" in body
        assert isinstance(body["job_id"], str)


class TestJobsEndpoint:
    def test_list_jobs(self, client: TestClient) -> None:
        client.post("/generate", json={"prompt": "test"})
        resp = client.get("/jobs")
        assert resp.status_code == 200
        jobs = resp.json()
        assert isinstance(jobs, list)
        assert len(jobs) >= 1

    def test_get_job_not_found(self, client: TestClient) -> None:
        resp = client.get("/jobs/nonexistent")
        assert resp.status_code == 404


class TestArtifactsEndpoint:
    def test_artifact_not_found(self, client: TestClient) -> None:
        resp = client.get("/artifacts/missing")
        assert resp.status_code == 404

    def test_artifact_meta_not_found(self, client: TestClient) -> None:
        resp = client.get("/artifacts/missing/meta")
        assert resp.status_code == 404
