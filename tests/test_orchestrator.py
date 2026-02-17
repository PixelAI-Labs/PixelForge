"""Tests for the Orchestrator — FIFO queue and GPU mutex.

Uses only core domain objects (no ML).
"""

import asyncio

import pytest

from core.models import Job, JobState
from orchestrator.orchestrator import Orchestrator


class TestOrchestrator:
    def test_submit_and_get(self) -> None:
        orch = Orchestrator()
        job = Job(prompt="test")
        job_id = orch.submit(job)
        assert orch.get_job(job_id) is job

    def test_list_jobs(self) -> None:
        orch = Orchestrator()
        j1 = Job(prompt="one")
        j2 = Job(prompt="two")
        orch.submit(j1)
        orch.submit(j2)
        jobs = orch.list_jobs()
        assert len(jobs) == 2
        assert jobs[0].prompt == "one"
        assert jobs[1].prompt == "two"

    def test_cancel_pending(self) -> None:
        orch = Orchestrator()
        job = Job(prompt="cancel me")
        orch.submit(job)
        assert orch.cancel(job.job_id) is True
        assert job.state == JobState.CANCELLED

    def test_cancel_nonexistent(self) -> None:
        orch = Orchestrator()
        assert orch.cancel("nope") is False

    @pytest.mark.asyncio
    async def test_run_job_success(self) -> None:
        orch = Orchestrator()
        job = Job(prompt="success test")
        orch.submit(job)

        def execute(j: Job) -> None:
            j.mark_completed(best_attempt=1)

        await orch.run_job(job, execute)
        assert job.state == JobState.COMPLETED

    @pytest.mark.asyncio
    async def test_run_job_failure(self) -> None:
        orch = Orchestrator()
        job = Job(prompt="fail test")
        orch.submit(job)

        def execute(j: Job) -> None:
            raise RuntimeError("boom")

        await orch.run_job(job, execute)
        assert job.state == JobState.FAILED
        assert "boom" in (job.error or "")

    @pytest.mark.asyncio
    async def test_gpu_mutual_exclusion(self) -> None:
        """Two jobs should not run concurrently — GPU lock enforces serial execution."""
        orch = Orchestrator()
        execution_order: list[str] = []

        j1 = Job(prompt="first")
        j2 = Job(prompt="second")
        orch.submit(j1)
        orch.submit(j2)

        def make_fn(label: str):
            def execute(j: Job) -> None:
                execution_order.append(f"{label}_start")
                import time
                time.sleep(0.05)
                execution_order.append(f"{label}_end")
                j.mark_completed(best_attempt=1)
            return execute

        await asyncio.gather(
            orch.run_job(j1, make_fn("A")),
            orch.run_job(j2, make_fn("B")),
        )

        # One must finish before the other starts
        assert execution_order.index("A_end") < execution_order.index("B_start") or \
               execution_order.index("B_end") < execution_order.index("A_start")
