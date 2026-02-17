"""Job Orchestrator — FIFO queue with GPU mutex.

From DESIGN.md / ADR-002:
* Single-worker FIFO job queue
* GPU mutual exclusion
* Job lifecycle tracking (Pending → Running → Completed | Failed | Cancelled)
* Cooperative cancellation support
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import OrderedDict
from typing import Callable, Dict, List, Optional

from core.models import Job, JobState

logger = logging.getLogger(__name__)


class Orchestrator:
    """Manage FIFO job queue with single-GPU mutual exclusion."""

    def __init__(self) -> None:
        self._gpu_lock = asyncio.Lock()
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._cancelled: set[str] = set()

    # ---- job management -----------------------------------------

    def submit(self, job: Job) -> str:
        """Enqueue a job and return its ID."""
        self._jobs[job.job_id] = job
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
            return

        async with self._gpu_lock:
            job.mark_running()
            logger.info("Job %s running.", job.job_id)
            try:
                # Execute in a thread so the event-loop is not blocked
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, execute_fn, job)
            except Exception as exc:
                logger.exception("Job %s failed.", job.job_id)
                job.mark_failed(str(exc))
