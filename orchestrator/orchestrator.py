"""Job Orchestrator — FIFO queue with GPU mutex.

From DESIGN.md / ADR-002:
* Single-worker FIFO job queue
* GPU mutual exclusion
* Job lifecycle tracking (Pending → Running → Completed | Failed | Cancelled)
* Cooperative cancellation support
* MongoDB persistence for job state
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import OrderedDict
from typing import Callable, Dict, List, Optional

from core.models import AttemptRecord, Job, JobState

logger = logging.getLogger(__name__)


def _job_to_doc(job: Job) -> dict:
    """Serialise a Job dataclass to a MongoDB document."""
    return {
        "job_id": job.job_id,
        "prompt": job.prompt,
        "negative_prompt": job.negative_prompt,
        "seed": job.seed,
        "state": job.state.value,
        "attempts": [
            {
                "attempt_number": a.attempt_number,
                "seed": a.seed,
                "steps": a.steps,
                "guidance_scale": a.guidance_scale,
                "width": a.width,
                "height": a.height,
                "quality_score": a.quality_score,
                "generation_time": a.generation_time,
                "image_key": a.image_key,
            }
            for a in job.attempts
        ],
        "best_attempt": job.best_attempt,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "error": job.error,
    }


def _doc_to_job(doc: dict) -> Job:
    """Deserialise a MongoDB document to a Job dataclass."""
    job = Job(
        prompt=doc["prompt"],
        job_id=doc["job_id"],
        state=JobState(doc["state"]),
        negative_prompt=doc.get("negative_prompt", ""),
        seed=doc.get("seed"),
        best_attempt=doc.get("best_attempt"),
        created_at=doc["created_at"],
        completed_at=doc.get("completed_at"),
        error=doc.get("error"),
    )
    for a in doc.get("attempts", []):
        job.attempts.append(AttemptRecord(
            attempt_number=a["attempt_number"],
            seed=a["seed"],
            steps=a["steps"],
            guidance_scale=a["guidance_scale"],
            width=a.get("width", 512),
            height=a.get("height", 512),
            quality_score=a.get("quality_score", 0.0),
            generation_time=a.get("generation_time", 0.0),
            image_key=a.get("image_key"),
        ))
    return job


class Orchestrator:
    """Manage FIFO job queue with single-GPU mutual exclusion.

    When *db* is provided (pymongo sync Database), jobs are persisted
    to the ``jobs`` collection.  Otherwise falls back to in-memory.
    """

    def __init__(self, db=None) -> None:
        self._gpu_lock: Optional[asyncio.Lock] = None
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._cancelled: set[str] = set()
        self._db = db
        self._col = db["jobs"] if db is not None else None

        # Reload persisted jobs into memory on startup
        if self._col is not None:
            for doc in self._col.find().sort("created_at", 1):
                job = _doc_to_job(doc)
                self._jobs[job.job_id] = job
            if self._jobs:
                logger.info("Restored %d jobs from MongoDB.", len(self._jobs))

    def _persist(self, job: Job) -> None:
        """Upsert job document to MongoDB (no-op if no DB)."""
        if self._col is not None:
            self._col.replace_one(
                {"job_id": job.job_id},
                _job_to_doc(job),
                upsert=True,
            )

    def _get_lock(self) -> asyncio.Lock:
        """Lazily create the asyncio lock inside a running event loop."""
        if self._gpu_lock is None:
            self._gpu_lock = asyncio.Lock()
        return self._gpu_lock

    # ---- job management -----------------------------------------

    def submit(self, job: Job) -> str:
        """Enqueue a job and return its ID."""
        self._jobs[job.job_id] = job
        self._persist(job)
        logger.info("Job %s submitted (queue size: %d)", job.job_id, len(self._jobs))
        return job.job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> List[Job]:
        return list(self._jobs.values())

    def cancel(self, job_id: str) -> bool:
        """Request cooperative cancellation of a job."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.state == JobState.PENDING:
            job.mark_cancelled()
            self._persist(job)
            self._cancelled.add(job_id)
            return True
        if job.state == JobState.RUNNING:
            self._cancelled.add(job_id)
            return True
        return False

    def is_cancelled(self, job_id: str) -> bool:
        return job_id in self._cancelled

    # ---- execution ----------------------------------------------

    async def run_job(
        self,
        job: Job,
        execute_fn: Callable[[Job], None],
    ) -> None:
        """Acquire GPU lock, run the job, and update state."""
        if self.is_cancelled(job.job_id):
            job.mark_cancelled()
            self._persist(job)
            return

        async with self._get_lock():
            job.mark_running()
            self._persist(job)
            logger.info("Job %s running.", job.job_id)
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, execute_fn, job)
                self._persist(job)
            except Exception as exc:
                logger.exception("Job %s failed.", job.job_id)
                job.mark_failed(str(exc))
                self._persist(job)
