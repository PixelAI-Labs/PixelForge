# PixelForge Workflow

This document describes runtime behavior from startup through generation, editing sessions, and shutdown.

## 1. Startup Workflow

1. main.py configures logging.
2. ModelManager is initialized (unless PIXELFORGE_SKIP_LOAD=1).
3. QualityEvaluator is initialized and CLIP is loaded (when not skip-load mode).
4. PromptPipeline is initialized.
5. MongoDB sync ping runs through db/connection.py.
6. FastAPI app is created with Mongo-backed or in-memory stores.

Outcome:

- If MongoDB is available, persistence mode is enabled.
- If MongoDB is unavailable, app continues in in-memory mode.

## 2. Auth Workflow

### Register

1. POST /auth/register validates input.
2. Store checks duplicate email/username.
3. Password is bcrypt-hashed and user is saved.
4. JWT is issued and returned.

### Login

1. POST /auth/login fetches user by email.
2. Password is verified.
3. JWT is issued and returned.

### Protected Calls

1. Auth dependency reads bearer token.
2. Token is decoded and validated.
3. Route receives payload with user id/username.

## 3. Generation Job Workflow

1. Frontend sends POST /generate with prompt data.
2. API creates a new job and submits to orchestrator.
3. Background task runs orchestrator.run_job.
4. Orchestrator acquires GPU lock and marks job running.
5. AdaptiveSampler executes attempts:
   - prompt processing
   - image generation
   - quality scoring
   - parameter adjustment on low score
6. All generated images are persisted as artifacts.
7. Attempt metadata is persisted.
8. Job is marked completed or failed.
9. Frontend polls GET /jobs/{job_id} until terminal state.
10. Frontend fetches GET /jobs/{job_id}/image for display.

## 4. Iterative Session Workflow

1. POST /generate-session creates EditSession and runs initial generation.
2. Iteration 0 image is saved and session is persisted.
3. POST /edit applies instruction to latest image through img2img.
4. New iteration image is saved and session timeline grows.
5. GET /sessions and GET /sessions/{id} expose active state.
6. DELETE /sessions/{id} ends the session and promotes final image to gallery/jobs.

## 5. Persistence Workflow

### Mongo Mode

- users, jobs, artifacts, artifact_meta, edit_sessions collections are used.
- startup restores previously saved sessions.
- shutdown flushes active sessions and closes DB clients.

### In-Memory Mode

- data is process-local and not durable across restarts.

## 6. Error and Retry Workflow

- Invalid token: 401/403 depending on route/auth context.
- Missing resource: 404.
- Session invalid state (no base image yet): 409.
- Model unavailable: 503.
- CUDA OOM in generation:
  - cache cleared
  - attempt recorded
  - sampler continues with reduced pressure settings.

## 7. Operational Sequence (Condensed)

```text
Client -> API -> Orchestrator -> Sampler -> Model + Evaluator -> Store -> API -> Client
```

Key invariant:

- only one GPU generation job executes at a time in a process.
