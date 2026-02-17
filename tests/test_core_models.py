"""Tests for core domain models — Job and JobState.

No ML imports required (per DESIGN.md: core/ must contain domain logic only).
"""

import time

from core.models import AttemptRecord, Job, JobState


class TestJobState:
    def test_states_exist(self) -> None:
        assert JobState.PENDING.value == "pending"
        assert JobState.RUNNING.value == "running"
        assert JobState.COMPLETED.value == "completed"
        assert JobState.FAILED.value == "failed"
        assert JobState.CANCELLED.value == "cancelled"


class TestJob:
    def test_creation_defaults(self) -> None:
        job = Job(prompt="a cat")
        assert job.prompt == "a cat"
        assert job.state == JobState.PENDING
        assert job.attempts == []
        assert job.best_attempt is None
        assert job.job_id  # non-empty

    def test_mark_running(self) -> None:
        job = Job(prompt="test")
        job.mark_running()
        assert job.state == JobState.RUNNING

    def test_mark_completed(self) -> None:
        job = Job(prompt="test")
        job.mark_running()
        job.mark_completed(best_attempt=1)
        assert job.state == JobState.COMPLETED
        assert job.best_attempt == 1
        assert job.completed_at is not None

    def test_mark_failed(self) -> None:
        job = Job(prompt="test")
        job.mark_running()
        job.mark_failed("GPU error")
        assert job.state == JobState.FAILED
        assert job.error == "GPU error"
        assert job.completed_at is not None

    def test_mark_cancelled(self) -> None:
        job = Job(prompt="test")
        job.mark_cancelled()
        assert job.state == JobState.CANCELLED

    def test_add_attempt(self) -> None:
        job = Job(prompt="test")
        rec = AttemptRecord(
            attempt_number=1,
            seed=42,
            steps=30,
            guidance_scale=7.5,
            width=512,
            height=512,
            quality_score=0.75,
            generation_time=5.0,
        )
        job.add_attempt(rec)
        assert len(job.attempts) == 1
        assert job.attempts[0].seed == 42

    def test_best_score(self) -> None:
        job = Job(prompt="test")
        job.add_attempt(AttemptRecord(1, 1, 30, 7.5, 512, 512, quality_score=0.5))
        job.add_attempt(AttemptRecord(2, 2, 40, 8.0, 512, 512, quality_score=0.8))
        assert job.best_score() == 0.8

    def test_best_score_empty(self) -> None:
        job = Job(prompt="test")
        assert job.best_score() == 0.0

    def test_to_dict(self) -> None:
        job = Job(prompt="test prompt")
        d = job.to_dict()
        assert d["prompt"] == "test prompt"
        assert d["state"] == "pending"
        assert d["attempts"] == 0
        assert d["best_score"] == 0.0

    def test_state_transitions_lifecycle(self) -> None:
        """Full lifecycle: pending → running → completed."""
        job = Job(prompt="lifecycle test")
        assert job.state == JobState.PENDING
        job.mark_running()
        assert job.state == JobState.RUNNING
        job.mark_completed(best_attempt=2)
        assert job.state == JobState.COMPLETED
        assert job.best_attempt == 2
