"""Core domain models for PixelForge.

This module contains domain logic only — no ML imports allowed.
"""

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class JobState(enum.Enum):
    """Lifecycle states for a generation job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AttemptRecord:
    """Metadata for a single generation attempt."""

    attempt_number: int
    seed: int
    steps: int
    guidance_scale: float
    width: int
    height: int
    quality_score: float = 0.0
    generation_time: float = 0.0
    image_key: Optional[str] = None


@dataclass
class Job:
    """Represents a single image-generation job.

    Tracks prompt, parameters, attempts, and lifecycle state.
    """

    prompt: str
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: JobState = JobState.PENDING
    attempts: List[AttemptRecord] = field(default_factory=list)
    best_attempt: Optional[int] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None
    negative_prompt: str = ""
    seed: Optional[int] = None

    # ---- state-transition helpers --------------------------------

    def mark_running(self) -> None:
        self.state = JobState.RUNNING

    def mark_completed(self, best_attempt: int) -> None:
        self.state = JobState.COMPLETED
        self.best_attempt = best_attempt
        self.completed_at = time.time()

    def mark_failed(self, error: str) -> None:
        self.state = JobState.FAILED
        self.error = error
        self.completed_at = time.time()

    def mark_cancelled(self) -> None:
        self.state = JobState.CANCELLED
        self.completed_at = time.time()

    def add_attempt(self, record: AttemptRecord) -> None:
        self.attempts.append(record)

    # ---- read helpers -------------------------------------------

    def best_score(self) -> float:
        if not self.attempts:
            return 0.0
        return max(a.quality_score for a in self.attempts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "prompt": self.prompt,
            "state": self.state.value,
            "attempts": len(self.attempts),
            "best_score": round(self.best_score(), 4),
            "best_attempt": self.best_attempt,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }
