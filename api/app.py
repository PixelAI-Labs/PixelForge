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
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from pydantic import BaseModel, Field

from auth.dependencies import get_current_user
from auth.router import init_user_store, router as auth_router
from auth.store import UserStore
from core.models import AttemptRecord, EditSession, Iteration, Job
from db.connection import (
    close_clients,
    ensure_indexes,
    get_sync_db,
    ping_mongo,
)
from engines.adaptive_sampler import AdaptiveSampler
from engines.iterative_generator import IterativeGenerator
from engines.model_manager import ModelManager
from engines.prompt_pipeline import PromptPipeline
from engines.quality_evaluator import QualityEvaluator
from orchestrator.orchestrator import Orchestrator
from store.artifact_store import InMemoryArtifactStore, MongoArtifactStore

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
    state: str
    prompt: str = ""
    attempts: int
    best_score: float
    error: Optional[str] = None


class EditRequest(BaseModel):
    session_id: str
    edit_instruction: str
    strength: float = Field(0.35, ge=0.0, le=1.0)


class EditResponse(BaseModel):
    session_id: str
    iteration: int


# ---- app factory ------------------------------------------------

def create_app(
    model_manager: Optional[ModelManager] = None,
    quality_evaluator: Optional[QualityEvaluator] = None,
    prompt_pipeline: Optional[PromptPipeline] = None,
    quality_threshold: float = 0.65,
    use_memory: bool = False,
) -> FastAPI:
    """Build and return a configured FastAPI application.

    Parameters
    ----------
    use_memory : bool
        If True, use in-memory stores instead of MongoDB (useful for tests).
    """

    app = FastAPI(title="PixelForge", version="0.1.0")

    # CORS — allow frontend dev server and Docker container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if use_memory:
        # In-memory stores for testing (no MongoDB required)
        from tests._inmemory_user_store import InMemoryUserStore
        user_store = InMemoryUserStore()  # type: ignore[arg-type]
        init_user_store(user_store)
        app.include_router(auth_router)
        store = InMemoryArtifactStore()
        orch = Orchestrator()
    else:
        # MongoDB-backed stores (production)
        sync_db = get_sync_db()
        user_store = UserStore(sync_db)  # type: ignore[arg-type]
        init_user_store(user_store)
        app.include_router(auth_router)
        store = MongoArtifactStore(sync_db)
        orch = Orchestrator(db=sync_db)

        @app.on_event("startup")
        async def _startup() -> None:
            await ping_mongo()
            await ensure_indexes()
            # Restore edit sessions from MongoDB
            try:
                restored = store.load_sessions()
                edit_sessions.update(restored)
                if restored:
                    logger.info("Restored %d edit sessions from MongoDB.", len(restored))
            except Exception:
                logger.warning("Could not restore edit sessions.", exc_info=True)

        @app.on_event("shutdown")
        async def _shutdown() -> None:
            # Promote active sessions to gallery and flush to MongoDB
            for s in edit_sessions.values():
                try:
                    _persist_session_result(s)
                except Exception:
                    logger.warning("Failed to promote session %s on shutdown.", s.session_id)
                try:
                    store.save_session(s)
                except Exception:
                    logger.warning("Failed to flush session %s on shutdown.", s.session_id)
            close_clients()

    mm = model_manager or ModelManager(auto_load=False)
    qe = quality_evaluator or QualityEvaluator()
    pp = prompt_pipeline
    sampler = AdaptiveSampler(
        mm, qe,
        quality_threshold=quality_threshold,
        prompt_pipeline=pp,
    )
    itergen = IterativeGenerator(mm, prompt_pipeline=pp)

    # session_id -> EditSession (persisted to MongoDB automatically)
    edit_sessions: Dict[str, EditSession] = {}
    _persisted_session_jobs: set[str] = set()  # session_ids already promoted to gallery

    def _persist_session(session: EditSession) -> None:
        """Save session state to the backing store."""
        try:
            store.save_session(session)
        except Exception:
            logger.warning("Failed to persist session %s", session.session_id, exc_info=True)

    def _persist_session_result(session: EditSession) -> None:
        """Promote the final iteration of a session to the gallery as a Job.

        Creates a Job record with the session's final image so it appears
        in the jobs list / gallery alongside normal generations.
        Skips if already persisted (deduplication).
        """
        if session.session_id in _persisted_session_jobs:
            logger.info("Session %s already promoted to gallery — skipping.", session.session_id)
            return
        latest = session.latest_iteration
        if latest is None or latest.artifact_id is None:
            logger.info("Session %s has no completed iteration — skipping gallery promotion.", session.session_id)
            return

        # Build edit history summary
        edit_history = [
            {"iteration": it.iteration, "instruction": it.edit_instruction, "prompt": it.prompt}
            for it in session.iterations
            if it.edit_instruction
        ]

        # Create a Job so the result shows up in GET /jobs
        job = Job(
            prompt=latest.prompt,
            job_id=session.session_id,  # reuse session_id as job_id
            seed=None,
            user_id=session.user_id,
        )
        # Fabricate a single AttemptRecord pointing at the final image
        attempt = AttemptRecord(
            attempt_number=0,
            seed=0,
            steps=30,
            guidance_scale=7.0,
            width=512,
            height=512,
            quality_score=0.0,
            generation_time=0.0,
            image_key=latest.artifact_id,
        )
        job.add_attempt(attempt)
        job.mark_completed(best_attempt=0)
        job.created_at = session.created_at

        # Register in the orchestrator so GET /jobs returns it
        orch.submit(job)
        # Directly set completed state (already done above via mark_completed)
        orch._jobs[job.job_id] = job
        if orch._col is not None:
            from orchestrator.orchestrator import _job_to_doc
            orch._col.replace_one({"job_id": job.job_id}, _job_to_doc(job), upsert=True)

        # Save metadata so GET /jobs/{id}/image works
        store.save_metadata(
            job.job_id,
            latest.prompt,
            [attempt],
            0,
        )

        _persisted_session_jobs.add(session.session_id)
        logger.info(
            "Session %s promoted to gallery as job %s (prompt=%r, iterations=%d, edits=%d)",
            session.session_id, job.job_id, latest.prompt,
            len(session.iterations), len(edit_history),
        )

    def _current_user_id(current_user: Dict[str, Any]) -> str:
        user_id = str(current_user.get("sub", "")).strip()
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid authentication payload")
        return user_id

    def _user_owns_job(user_id: str, job_id: str) -> bool:
        job = orch.get_job(job_id)
        return job is not None and job.user_id == user_id

    def _user_owns_session(user_id: str, session_id: str) -> bool:
        session = edit_sessions.get(session_id)
        return session is not None and session.user_id == user_id

    def _user_owns_resource(user_id: str, resource_id: str) -> bool:
        return _user_owns_job(user_id, resource_id) or _user_owns_session(user_id, resource_id)

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
        if not bool(getattr(mm, "is_loaded", False)):
            raise HTTPException(
                status_code=503,
                detail="Image generation is unavailable — no GPU model loaded. "
                       "Set PIXELFORGE_SKIP_LOAD=0 on a CUDA-capable host.",
            )
        job = Job(
            prompt=req.prompt,
            seed=req.seed,
            negative_prompt=req.negative_prompt,
            user_id=_current_user_id(current_user),
        )
        orch.submit(job)
        background_tasks.add_task(orch.run_job, job, _execute_job)
        return GenerateResponse(job_id=job.job_id)

    @app.get("/jobs")
    async def list_jobs(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> list[Dict[str, Any]]:
        user_id = _current_user_id(current_user)
        return [j.to_dict() for j in orch.list_jobs() if j.user_id == user_id]

    @app.get("/jobs/{job_id}", response_model=JobStatusResponse)
    async def get_job(
        job_id: str,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> JobStatusResponse:
        user_id = _current_user_id(current_user)
        job = orch.get_job(job_id)
        if job is None or job.user_id != user_id:
            raise HTTPException(status_code=404, detail="Job not found")
        return JobStatusResponse(
            job_id=job.job_id,
            state=job.state.value,
            prompt=job.prompt,
            attempts=len(job.attempts),
            best_score=round(job.best_score(), 4),
            error=job.error,
        )

    @app.get("/artifacts/{artifact_id}")
    async def get_artifact(
        artifact_id: str,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Response:
        user_id = _current_user_id(current_user)
        resource_id = store.get_artifact_job_id(artifact_id)
        if resource_id is None or not _user_owns_resource(user_id, resource_id):
            raise HTTPException(status_code=404, detail="Artifact not found")
        data = store.get_image_bytes(artifact_id)
        if data is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return Response(content=data, media_type="image/png")

    @app.get("/jobs/{job_id}/image")
    async def get_job_image(
        job_id: str,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Response:
        """Return the best generated image for a completed job."""
        user_id = _current_user_id(current_user)
        if not _user_owns_job(user_id, job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        logger.info("Image request for job_id=%s", job_id)
        data = store.get_best_image_bytes(job_id)
        if data is None:
            logger.warning("No image found for job_id=%s", job_id)
            raise HTTPException(status_code=404, detail="No image found for this job")
        logger.info("Serving image for job_id=%s (%d bytes)", job_id, len(data))
        return Response(content=data, media_type="image/png")

    @app.get("/artifacts/{artifact_id}/meta")
    async def get_artifact_meta(
        artifact_id: str,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        user_id = _current_user_id(current_user)
        if not _user_owns_resource(user_id, artifact_id):
            raise HTTPException(status_code=404, detail="Metadata not found")
        # artifact_id is used as job_id in metadata lookup
        # Try finding metadata that references this artifact
        # For simplicity, expose job-level metadata via job_id
        meta = store.get_metadata(artifact_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Metadata not found")
        return meta

    # ---- iterative editing routes --------------------------------

    @app.post("/generate-session", response_model=EditResponse)
    async def generate_session(
        req: GenerateRequest,
        background_tasks: BackgroundTasks,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> EditResponse:
        """Create a new editing session with an initial image."""
        if mm._pipe is None and mm._device is None:
            raise HTTPException(status_code=503, detail="Model unavailable.")

        session = EditSession(
            original_prompt=req.prompt,
            user_id=_current_user_id(current_user),
        )

        def _run() -> None:
            image = itergen.generate_initial(
                prompt=req.prompt,
                seed=req.seed,
                negative_prompt=req.negative_prompt,
            )
            artifact_id = store.save_image(image, session.session_id, 0)
            it = Iteration(
                iteration=0,
                prompt=req.prompt,
                artifact_id=artifact_id,
            )
            session.add_iteration(it)
            _persist_session(session)

        edit_sessions[session.session_id] = session
        background_tasks.add_task(_run)
        return EditResponse(session_id=session.session_id, iteration=0)

    @app.post("/edit", response_model=EditResponse)
    async def edit_image(
        req: EditRequest,
        background_tasks: BackgroundTasks,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> EditResponse:
        """Apply an edit to the latest image in a session."""
        user_id = _current_user_id(current_user)
        session = edit_sessions.get(req.session_id)
        if session is None or session.user_id != user_id:
            raise HTTPException(status_code=404, detail="Session not found")
        latest = session.latest_iteration
        if latest is None or latest.artifact_id is None:
            raise HTTPException(status_code=409, detail="Session has no image yet")

        next_iter = len(session.iterations)

        def _run() -> None:
            # Load previous image from store
            prev_bytes = store.get_image_bytes(latest.artifact_id)
            if prev_bytes is None:
                logger.error("Previous image not found for session %s", req.session_id)
                return

            import io
            prev_image = Image.open(io.BytesIO(prev_bytes)).convert("RGB")

            result_image = itergen.edit_image(
                image=prev_image,
                original_prompt=latest.prompt,
                edit_instruction=req.edit_instruction,
                strength=req.strength,
            )
            merged_prompt = itergen.prompt_update(latest.prompt, req.edit_instruction)
            artifact_id = store.save_image(result_image, session.session_id, next_iter)
            it = Iteration(
                iteration=next_iter,
                prompt=merged_prompt,
                edit_instruction=req.edit_instruction,
                artifact_id=artifact_id,
            )
            session.add_iteration(it)
            _persist_session(session)

        background_tasks.add_task(_run)
        return EditResponse(session_id=req.session_id, iteration=next_iter)

    @app.get("/sessions")
    async def list_sessions(
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> List[Dict[str, Any]]:
        """Return all active edit sessions (summary only)."""
        user_id = _current_user_id(current_user)
        result = []
        for s in edit_sessions.values():
            if s.user_id != user_id:
                continue
            result.append({
                "session_id": s.session_id,
                "original_prompt": s.original_prompt,
                "iteration_count": len(s.iterations),
                "created_at": s.created_at,
            })
        return result

    @app.get("/sessions/{session_id}")
    async def get_session(
        session_id: str,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, Any]:
        user_id = _current_user_id(current_user)
        session = edit_sessions.get(session_id)
        if session is None or session.user_id != user_id:
            raise HTTPException(status_code=404, detail="Session not found")
        return session.to_dict()

    @app.get("/sessions/{session_id}/image/{iteration}")
    async def get_session_image(
        session_id: str,
        iteration: int,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Response:
        """Return the image for a specific iteration."""
        user_id = _current_user_id(current_user)
        session = edit_sessions.get(session_id)
        if session is None or session.user_id != user_id:
            raise HTTPException(status_code=404, detail="Session not found")
        for it in session.iterations:
            if it.iteration == iteration and it.artifact_id:
                data = store.get_image_bytes(it.artifact_id)
                if data:
                    return Response(content=data, media_type="image/png")
        raise HTTPException(status_code=404, detail="Image not found for this iteration")

    @app.delete("/sessions/{session_id}")
    async def end_session(
        session_id: str,
        current_user: Dict[str, Any] = Depends(get_current_user),
    ) -> Dict[str, str]:
        """End (close) an editing session."""
        user_id = _current_user_id(current_user)
        session = edit_sessions.get(session_id)
        if session is None or session.user_id != user_id:
            raise HTTPException(status_code=404, detail="Session not found")
        edit_sessions.pop(session_id, None)
        # Promote final iteration to gallery
        try:
            _persist_session_result(session)
        except Exception:
            logger.warning("Failed to promote session %s to gallery", session_id, exc_info=True)
        # Persist final state then remove from DB
        try:
            store.save_session(session)
        except Exception:
            logger.warning("Failed final save for session %s", session_id)
        try:
            store.delete_session(session_id)
        except Exception:
            logger.warning("Failed to delete session %s from store", session_id)
        return {"status": "ended", "session_id": session_id}

    return app
