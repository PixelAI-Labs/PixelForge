"""Tests for the ArtifactStore (in-memory implementation)."""

from PIL import Image

from core.models import AttemptRecord
from store.artifact_store import InMemoryArtifactStore


class TestInMemoryArtifactStore:
    def _make_image(self, w: int = 64, h: int = 64) -> Image.Image:
        return Image.new("RGB", (w, h), color="red")

    def test_save_and_retrieve_image(self) -> None:
        store = InMemoryArtifactStore()
        img = self._make_image()
        aid = store.save_image(img, "job1", 1)
        data = store.get_image_bytes(aid)
        assert data is not None
        assert len(data) > 0

    def test_missing_image(self) -> None:
        store = InMemoryArtifactStore()
        assert store.get_image_bytes("nonexistent") is None

    def test_save_and_retrieve_metadata(self) -> None:
        store = InMemoryArtifactStore()
        attempts = [
            AttemptRecord(1, 42, 30, 7.5, 512, 512, quality_score=0.6),
            AttemptRecord(2, 99, 40, 8.0, 512, 512, quality_score=0.8),
        ]
        store.save_metadata("job1", "a cat", attempts, selected=2)
        meta = store.get_metadata("job1")
        assert meta is not None
        assert meta["prompt"] == "a cat"
        assert len(meta["attempts"]) == 2
        assert meta["selected_attempt"] == 2

    def test_missing_metadata(self) -> None:
        store = InMemoryArtifactStore()
        assert store.get_metadata("nope") is None
