"""ArtifactStore — persist images and attempt metadata.

Implementations:
* InMemoryArtifactStore  – fallback when no DB is available (tests)
* MongoArtifactStore     – MongoDB-backed persistence (production)
"""

from __future__ import annotations

import io
import logging
import uuid
from typing import Any, Dict, List, Optional, Protocol

from PIL import Image

from core.models import AttemptRecord

logger = logging.getLogger(__name__)


# ---- abstract interface ----------------------------------------

class ArtifactStoreProtocol(Protocol):
    """Protocol every artifact store must satisfy."""

    def save_image(self, image: Image.Image, job_id: str, attempt: int) -> str: ...
    def get_image_bytes(self, artifact_id: str) -> Optional[bytes]: ...
    def get_best_image_bytes(self, job_id: str) -> Optional[bytes]: ...
    def save_metadata(self, job_id: str, prompt: str, attempts: List[AttemptRecord], selected: int) -> None: ...
    def get_metadata(self, job_id: str) -> Optional[Dict[str, Any]]: ...


# ---- in-memory implementation (kept for tests) -----------------

class InMemoryArtifactStore:
    """Simple in-memory store for images and metadata."""

    def __init__(self) -> None:
        self._images: Dict[str, bytes] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._job_artifacts: Dict[str, List[str]] = {}  # job_id -> [artifact_ids]

    def save_image(self, image: Image.Image, job_id: str, attempt: int) -> str:
        artifact_id = uuid.uuid4().hex
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        self._images[artifact_id] = buf.getvalue()
        self._job_artifacts.setdefault(job_id, []).append(artifact_id)
        return artifact_id

    def get_image_bytes(self, artifact_id: str) -> Optional[bytes]:
        return self._images.get(artifact_id)

    def get_best_image_bytes(self, job_id: str) -> Optional[bytes]:
        """Return the best (selected) image for a job, or the last one."""
        meta = self._meta.get(job_id)
        if meta:
            selected = meta.get("selected_attempt")
            for att in meta.get("attempts", []):
                if att["attempt"] == selected and att.get("image_key"):
                    return self._images.get(att["image_key"])
        # Fallback: return last artifact for this job
        aids = self._job_artifacts.get(job_id, [])
        if aids:
            return self._images.get(aids[-1])
        return None

    def save_metadata(
        self, job_id: str, prompt: str,
        attempts: List[AttemptRecord], selected: int,
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


# ---- MongoDB implementation ------------------------------------

class MongoArtifactStore:
    """MongoDB-backed artifact store (sync pymongo).

    Collections used:
      artifacts     – { artifact_id, job_id, attempt, data (Binary) }
      artifact_meta – { job_id, prompt, attempts [...], selected_attempt }
    """

    def __init__(self, db) -> None:
        from pymongo.database import Database as SyncDatabase
        self._artifacts = db["artifacts"]
        self._meta = db["artifact_meta"]

    def save_image(self, image: Image.Image, job_id: str, attempt: int) -> str:
        import bson
        artifact_id = uuid.uuid4().hex
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        self._artifacts.insert_one({
            "artifact_id": artifact_id,
            "job_id": job_id,
            "attempt": attempt,
            "data": bson.Binary(buf.getvalue()),
        })
        return artifact_id

    def get_image_bytes(self, artifact_id: str) -> Optional[bytes]:
        doc = self._artifacts.find_one({"artifact_id": artifact_id})
        if doc is None:
            return None
        return bytes(doc["data"])

    def get_best_image_bytes(self, job_id: str) -> Optional[bytes]:
        """Return the best (selected) image for a job."""
        meta = self._meta.find_one({"job_id": job_id})
        logger.info("get_best_image_bytes job_id=%s — meta found: %s", job_id, meta is not None)
        if meta:
            selected = meta.get("selected_attempt")
            logger.info("  selected_attempt=%s, attempts=%d", selected, len(meta.get("attempts", [])))
            for att in meta.get("attempts", []):
                logger.info("  attempt=%s image_key=%s", att.get("attempt"), att.get("image_key"))
                if att["attempt"] == selected and att.get("image_key"):
                    return self.get_image_bytes(att["image_key"])
        # Fallback: return the last artifact for this job
        doc = self._artifacts.find_one(
            {"job_id": job_id}, sort=[("attempt", -1)]
        )
        logger.info("  fallback artifact found: %s", doc is not None)
        if doc:
            return bytes(doc["data"])
        return None

    def save_metadata(
        self, job_id: str, prompt: str,
        attempts: List[AttemptRecord], selected: int,
    ) -> None:
        doc = {
            "job_id": job_id,
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
        self._meta.replace_one({"job_id": job_id}, doc, upsert=True)

    def get_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        doc = self._meta.find_one({"job_id": job_id}, {"_id": 0})
        return doc
