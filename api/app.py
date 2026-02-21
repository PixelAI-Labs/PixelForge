"""FastAPI application factory and routers.

Endpoints (from API.md / DESIGN.md):
* POST /generate          – submit generation request
* GET  /jobs              – list all jobs
* GET  /jobs/{job_id}     – get job status
* GET  /artifacts/{id}    – retrieve image (PNG)
* GET  /artifacts/{id}/meta – retrieve attempt metadata
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from auth.dependencies import get_current_user
from auth.router import init_user_store, router as auth_router
from auth.store import UserStore
from core.models import AttemptRecord, Job
from engines.adaptive_sampler import AdaptiveSampler
from engines.model_manager import ModelManager
from engines.quality_evaluator import QualityEvaluator
from orchestrator.orchestrator import Orchestrator
from store.artifact_store import InMemoryArtifactStore

logger = logging.getLogger(__name__)


# ---- request / response schemas --------------------------------

class GenerateRequest(BaseModel):
    prompt: str
    seed: Optional[int] = None
    negative_prompt: str = ""


class GenerateResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    attempts: int
    best_score: float
    error: Optional[str] = None


# ---- app factory ------------------------------------------------

def create_app(
    model_manager: Optional[ModelManager] = None,
    quality_evaluator: Optional[QualityEvaluator] = None,
    quality_threshold: float = 0.65,
) -> FastAPI:
    """Build and return a configured FastAPI application."""

    app = FastAPI(title="PixelForge", version="0.1.0")

    # CORS — allow frontend dev server and Docker container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth setup
    user_store = UserStore()
    init_user_store(user_store)
    app.include_router(auth_router)

    store = InMemoryArtifactStore()
    orch = Orchestrator()

    mm = model_manager or ModelManager(auto_load=False)
    qe = quality_evaluator or QualityEvaluator()
    sampler = AdaptiveSampler(mm, qe, quality_threshold=quality_threshold)

    # ---- helpers ------------------------------------------------

    def _execute_job(job: Job) -> None:
        """Blocking function executed inside the orchestrator thread."""
        result = sampler.run(
            prompt=job.prompt,
            seed=job.seed,
            negative_prompt=job.negative_prompt,
        )

        # Persist images and update records
        for i, rec in enumerate(result.attempts):
            img = result.images[i] if i < len(result.images) else None
            if img is None:
                continue  # skip OOM / failed attempts with no image
            artifact_id = store.save_image(
                img,
                job.job_id,
                rec.attempt_number,
            )
            rec.image_key = artifact_id

        # Save metadata
        store.save_metadata(
            job.job_id,
            job.prompt,
            result.attempts,
            result.best_attempt,
        )

        # Update job model
        for rec in result.attempts:
            job.add_attempt(rec)
        job.mark_completed(result.best_attempt)

    # ---- routes -------------------------------------------------

    @app.post("/generate", response_model=GenerateResponse)
    async def generate(
        req: GenerateRequest,
        background_tasks: BackgroundTasks,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> GenerateResponse:
        if mm._pipe is None and mm._device is None:
            raise HTTPException(
                status_code=503,
                detail="Image generation is unavailable — no GPU model loaded. "
                       "Set PIXELFORGE_SKIP_LOAD=0 on a CUDA-capable host.",
            )
        job = Job(prompt=req.prompt, seed=req.seed, negative_prompt=req.negative_prompt)
        orch.submit(job)
        background_tasks.add_task(orch.run_job, job, _execute_job)
        return GenerateResponse(job_id=job.job_id)

    @app.get("/jobs")
    async def list_jobs() -> list[Dict[str, Any]]:
        return [j.to_dict() for j in orch.list_jobs()]

    @app.get("/jobs/{job_id}", response_model=JobStatusResponse)
    async def get_job(job_id: str) -> JobStatusResponse:
        job = orch.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return JobStatusResponse(
            job_id=job.job_id,
            status=job.state.value,
            attempts=len(job.attempts),
            best_score=round(job.best_score(), 4),
            error=job.error,
        )

    @app.get("/artifacts/{artifact_id}")
    async def get_artifact(artifact_id: str) -> Response:
        data = store.get_image_bytes(artifact_id)
        if data is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return Response(content=data, media_type="image/png")

    @app.get("/artifacts/{artifact_id}/meta")
    async def get_artifact_meta(artifact_id: str) -> Dict[str, Any]:
        # artifact_id is used as job_id in metadata lookup
        # Try finding metadata that references this artifact
        # For simplicity, expose job-level metadata via job_id
        meta = store.get_metadata(artifact_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Metadata not found")
        return meta

    return app
