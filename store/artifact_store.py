"""ArtifactStore — persist images and attempt metadata.

Implementations (from DESIGN.md):
* InMemoryStore  – fallback when no DB is available
* (MongoDB store – placeholder for future)
"""

from __future__ import annotations

import io
import uuid
from typing import Any, Dict, List, Optional, Protocol

from PIL import Image

from core.models import AttemptRecord


# ---- abstract interface ----------------------------------------

class ArtifactStoreProtocol(Protocol):
    """Protocol every artifact store must satisfy."""

    def save_image(self, image: Image.Image, job_id: str, attempt: int) -> str:
        """Persist an image and return an artifact ID."""
        ...

    def get_image_bytes(self, artifact_id: str) -> Optional[bytes]:
        """Retrieve raw PNG bytes by artifact ID."""
        ...

    def save_metadata(self, job_id: str, prompt: str, attempts: List[AttemptRecord], selected: int) -> None:
        """Persist attempt metadata for a job."""
        ...

    def get_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve metadata for a job."""
        ...


# ---- in-memory implementation ----------------------------------

class InMemoryArtifactStore:
    """Simple in-memory store for images and metadata."""

    def __init__(self) -> None:
        self._images: Dict[str, bytes] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}

    def save_image(self, image: Image.Image, job_id: str, attempt: int) -> str:
        artifact_id = uuid.uuid4().hex
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        self._images[artifact_id] = buf.getvalue()
        return artifact_id

    def get_image_bytes(self, artifact_id: str) -> Optional[bytes]:
        return self._images.get(artifact_id)

    def save_metadata(
        self,
        job_id: str,
        prompt: str,
        attempts: List[AttemptRecord],
        selected: int,
    ) -> None:
        self._meta[job_id] = {
            "prompt": prompt,
            "attempts": [
                {
                    "attempt": a.attempt_number,
                    "seed": a.seed,
                    "steps": a.steps,
                    "guidance_scale": a.guidance_scale,
                    "quality_score": round(a.quality_score, 4),
                    "generation_time": round(a.generation_time, 3),
                    "image_key": a.image_key,
                }
                for a in attempts
            ],
            "selected_attempt": selected,
        }

    def get_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self._meta.get(job_id)
