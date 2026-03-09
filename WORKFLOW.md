# PixelForge — System Workflow & Architecture

> End-to-end description of how a user prompt becomes a generated image, including architecture decisions, design principles, and deployment topology.

For a complete function-level reference, see [IMPLEMENTED.md](IMPLEMENTED.md).  
For unimplemented stubs and future roadmap, see [UNIMPLEMENTED.md](UNIMPLEMENTED.md).

---

## Table of Contents

1. [High-Level Overview](#1-high-level-overview)
2. [Startup Sequence](#2-startup-sequence)
3. [Authentication Flow](#3-authentication-flow)
4. [Image Generation Flow](#4-image-generation-flow)
   - 4.1 [Frontend Submission](#41-frontend-submission)
   - 4.2 [API Layer](#42-api-layer)
   - 4.3 [Orchestrator Scheduling](#43-orchestrator-scheduling)
   - 4.4 [Prompt Pipeline](#44-prompt-pipeline)
   - 4.5 [Adaptive Sampling Loop](#45-adaptive-sampling-loop)
   - 4.6 [Image Generation (Stable Diffusion)](#46-image-generation-stable-diffusion)
   - 4.7 [Quality Evaluation](#47-quality-evaluation)
   - 4.8 [Artifact Persistence](#48-artifact-persistence)
5. [Iterative Editing Flow](#5-iterative-editing-flow)
6. [Job Polling & Image Retrieval](#6-job-polling--image-retrieval)
7. [Data Flow Diagram](#7-data-flow-diagram)
8. [Component Interaction Map](#8-component-interaction-map)
9. [Error Handling](#9-error-handling)
10. [Deployment Topology](#10-deployment-topology)
11. [Architecture Decisions](#11-architecture-decisions)
12. [Design Principles](#12-design-principles)
13. [Technology Stack](#13-technology-stack)

---

## 1. High-Level Overview

```
User ──► React SPA ──► FastAPI ──► Orchestrator ──► AdaptiveSampler
                                                      │
                                          ┌───────────┼───────────┐
                                          ▼           ▼           ▼
                                   PromptPipeline  ModelManager  QualityEvaluator
                                   (SymSpell +     (SD 1.5       (CLIP + Sharpness)
                                    Flan-T5)       txt2img +
                                                    img2img)
                                                      │
                                                      ▼
                                               ArtifactStore ──► MongoDB
```

A user types a text prompt in the React frontend. The prompt travels through a FastAPI endpoint, is queued by the Orchestrator, preprocessed by the PromptPipeline, and fed into a feedback-driven adaptive sampling loop. Stable Diffusion 1.5 generates images which are scored by CLIP alignment and Laplacian sharpness. The best image is persisted to MongoDB and served back to the frontend. Users can also create **iterative editing sessions** where they generate an initial image and then apply incremental edits (e.g. "add neon lights") via img2img.

---

## 2. Startup Sequence

**Entry point:** `main.py`

| Step | Action | Module |
|------|--------|--------|
| 1 | Configure logging | `main.py` |
| 2 | Instantiate `ModelManager` — loads SD 1.5 onto CUDA GPU | `engines/model_manager.py` |
| 3 | Instantiate `QualityEvaluator` — loads CLIP ViT-B/32 | `engines/quality_evaluator.py` |
| 4 | Instantiate `PromptPipeline` (lazy-loads SymSpell + Flan-T5 on first use) | `engines/prompt_pipeline.py` |
| 5 | Verify MongoDB connectivity via `verify_sync_connection()` | `db/connection.py` |
| 6 | Call `create_app()` — wire middleware, auth, routes, stores | `api/app.py` |
| 7 | Uvicorn serves the FastAPI application on port 8000 | — |

If `PIXELFORGE_SKIP_LOAD=1` is set (test mode), model loading is deferred and the pipeline is disabled.

If MongoDB is unreachable, the app falls back to in-memory stores automatically.

---

## 3. Authentication Flow

All generation endpoints require a valid JWT token.

```
┌──────────┐        POST /auth/register         ┌──────────┐
│  Client  │ ──────────────────────────────────► │  FastAPI  │
│  (React) │ ◄────── { access_token, user_id } ──│  /auth/*  │
│          │                                     │          │
│          │        POST /auth/login             │          │
│          │ ──────────────────────────────────► │          │
│          │ ◄────── { access_token, user_id } ──│          │
└──────────┘                                     └──────────┘
```

### Registration (`POST /auth/register`)
1. Validate username (3-30 chars), email, password (≥6 chars)
2. Check uniqueness (email + username) against `UserStore`
3. Hash password with **bcrypt**
4. Persist `User` document to MongoDB `users` collection
5. Generate **JWT** (HS256, 24h expiry) containing `sub` (user_id) and `username`
6. Return token to client

### Login (`POST /auth/login`)
1. Look up user by email
2. Verify password against bcrypt hash
3. Return new JWT

### Token Validation
- Every protected endpoint uses `Depends(get_current_user)`
- Extracts `Authorization: Bearer <token>` header
- Decodes JWT with `decode_access_token()` — rejects expired/invalid tokens
- Returns `{ sub, username }` payload to the route handler

---

## 4. Image Generation Flow

### 4.1 Frontend Submission

**File:** `frontend/src/pages/Generate.jsx`

1. User fills in **prompt**, optional **negative prompt**, optional **seed**
2. Clicks "Generate" → calls `generateImage(prompt, seed, negativePrompt)` in `api.js`
3. `api.js` sends `POST /generate` with JSON body `{ prompt, seed, negative_prompt }` and `Authorization` header
4. Backend returns `{ job_id }` — the frontend stores it and starts polling

### 4.2 API Layer

**File:** `api/app.py` → `POST /generate`

1. Dependency `get_current_user` validates the JWT (rejects 401 if invalid)
2. Guard: if `ModelManager._pipe is None` → return **503** (no GPU loaded)
3. Create a `Job` dataclass (state = `PENDING`, auto-generated UUID)
4. `Orchestrator.submit(job)` — registers the job and persists to MongoDB
5. `BackgroundTasks.add_task(orch.run_job, job, _execute_job)` — schedules async execution
6. Return `{ job_id }` immediately (non-blocking to the client)

### 4.3 Orchestrator Scheduling

**File:** `orchestrator/orchestrator.py`

1. `run_job()` checks cooperative cancellation flag
2. Acquires **async GPU lock** (`asyncio.Lock`) — ensures only one job uses the GPU at a time
3. Marks job as `RUNNING` and persists state to MongoDB
4. Runs `_execute_job(job)` inside `loop.run_in_executor(None, ...)` — offloads blocking GPU work to a thread
5. On success: persists final state. On exception: marks job as `FAILED`

### 4.4 Prompt Pipeline

**File:** `engines/prompt_pipeline.py`

The prompt passes through three preprocessing stages before reaching Stable Diffusion:

```
  "dragn flyng in nite city"
           │
           ▼
  ┌─── Stage 1: Spelling ───┐
  │  SymSpell lookup_compound│
  │  → "dragon flying in     │
  │     night city"          │
  └──────────┬───────────────┘
             ▼
  ┌─── Stage 2: Grammar ────┐
  │  Flan-T5-small           │
  │  "Correct the grammar    │
  │   of this sentence: …"  │
  │  → "dragon flying in     │
  │     site city"           │
  └──────────┬───────────────┘
             ▼
  ┌─── Stage 3: Enhancement ─┐
  │  Rule-based:              │
  │  • Prefix short prompts   │
  │    with "Highly detailed  │
  │     image of"             │
  │  • Append quality suffix  │
  │    if none present        │
  │  → "Highly detailed image │
  │     of dragon flying in   │
  │     site city, cinematic  │
  │     lighting, ultra sharp │
  │     focus, 4k resolution" │
  │                           │
  │  negative_prompt =        │
  │    "blurry, distorted,    │
  │     low resolution, extra │
  │     limbs, malformed      │
  │     anatomy"              │
  └───────────────────────────┘
```

**Thread-safety:** SymSpell dictionary and Flan-T5 model are loaded once via double-checked locking behind a `threading.Lock`.

### 4.5 Adaptive Sampling Loop

**File:** `engines/adaptive_sampler.py`

The core feedback loop that maximises image quality:

```
  attempt = 1
  ┌─────────────────────────────────────────────┐
  │  1. Generate image via ModelManager          │
  │  2. Score via QualityEvaluator (CLIP+sharp)  │
  │  3. If score ≥ threshold (0.80) → accept     │
  │  4. Else:                                    │
  │     • steps += 10  (max 100)                 │
  │     • cfg *= 1.1   (max 20.0)                │
  │     • new random seed                        │
  │     • strengthen negative prompt             │
  │  5. Clear CUDA cache                         │
  │  6. attempt += 1                             │
  └───────────────┬─────────────────────────────┘
                  │  repeat up to 10 attempts
                  ▼
           Return best image
```

The loop returns a `SamplingResult` containing:
- `best_image` — highest-scored PIL Image
- `best_attempt` — 1-indexed attempt number
- `attempts` — list of `AttemptRecord` with full metadata
- `images` — all generated images (including failed OOM placeholders)

### 4.6 Image Generation (Stable Diffusion)

**File:** `engines/model_manager.py`

`ModelManager.generate()` is the single txt2img interface to the diffusion model:

1. Create a `torch.Generator` seeded for reproducibility
2. Call the `StableDiffusionPipeline` with all parameters (prompt, negative_prompt, steps, CFG, dimensions)
3. Return the first output image as a `PIL.Image`

`ModelManager.img2img()` provides an img2img interface sharing the same weights:

1. Accept a source `PIL.Image`, prompt, and denoising strength
2. Call the `StableDiffusionImg2ImgPipeline` (reuses VAE, UNet, text encoder)
3. Return the transformed image

**Memory optimisations applied at load time:**
- Attention slicing
- VAE slicing
- xformers memory-efficient attention (if available)

**OOM handling:** On CUDA out-of-memory, clears cache and re-raises to let `AdaptiveSampler` retry with reduced parameters.

### 4.7 Quality Evaluation

**File:** `engines/quality_evaluator.py`

Each generated image is scored on two metrics:

| Metric | Weight | Method |
|--------|--------|--------|
| CLIP alignment | 0.5 | True cosine similarity between L2-normalised image and text embeddings via `openai/clip-vit-base-patch32`, remapped from [-1, 1] to [0, 1]. Falls back to 0 (sharpness-only) if CLIP cannot be loaded (e.g. offline with no cache). |
| Sharpness | 0.5 | Laplacian variance via OpenCV, normalised to 0–1 |
| Face detection | 0.0 | Placeholder (hardcoded to 0.0) |

**Combined score** = `(w_clip × clip + w_sharpness × sharpness) / total_weight`, clamped to [0, 1].

The adaptive loop compares this score against the threshold (default 0.80) to decide whether to accept or retry.

### 4.8 Artifact Persistence

**File:** `store/artifact_store.py`

After the adaptive loop completes, `_execute_job()` in `app.py`:

1. **Save images:** For each attempt, encode the PIL Image to PNG bytes and store in MongoDB `artifacts` collection (or in-memory dict)
2. **Save metadata:** Write a summary document to `artifact_meta` with all attempt records and the selected best attempt
3. **Update Job:** Attach `AttemptRecord`s to the `Job` object, mark as `COMPLETED` with the best attempt index. Orchestrator persists the final job state to MongoDB `jobs` collection

---

## 5. Iterative Editing Flow

The iterative editing system lets users refine images through successive img2img edits. Sessions can be listed, resumed, ended (promoting the result to the gallery), and are persisted to MongoDB.

**Files:** `engines/iterative_generator.py`, `engines/prompt_pipeline.py`, `api/app.py`

```
User: "A castle on a hill"
         │
         ▼  POST /generate-session
   IterativeGenerator.generate_initial()
     1. PromptPipeline.process(prompt)         ← spelling + grammar + enhance
     2. txt2img(enhanced_prompt, 512×512, 30 steps)
         │
         ▼
   Iteration 0: [castle image]  ← stored in ArtifactStore
         │
User: "add neon lights"
         │
         ▼  POST /edit  (strength=0.35)
   IterativeGenerator.edit_image()
     1. PromptPipeline.merge_edit("A castle on a hill", "add neon lights")
        → "A castle on a hill, neon lights"    ← strips imperative prefix
     2. PromptPipeline.process(merged)          ← enhance merged prompt
     3. img2img(prev_image, enhanced_prompt, strength=0.35)
         │
         ▼
   Iteration 1: [castle + neon]  ← stored in ArtifactStore
         │
User: "make it nighttime"
         │
         ▼  POST /edit  (strength=0.35)
   Iteration 2: [castle + neon + night]
         │
User clicks "End Session"
         │
         ▼  DELETE /sessions/{session_id}
   _persist_session_result(session)
     1. Creates a Job record from the final iteration
     2. Fabricates an AttemptRecord with quality_score=1.0
     3. Saves image metadata via ArtifactStore
     4. Registers job with Orchestrator → appears in gallery
     5. Deduplication: skips if session_id already in _persisted_session_jobs
         │
         ▼
   Session removed from active list, final image in gallery
```

### Session Lifecycle

1. **Create session** (`POST /generate-session`): Generates initial image via txt2img (enhanced by PromptPipeline), creates `EditSession` with `Iteration 0`, persists session to MongoDB
2. **Edit** (`POST /edit`): Loads previous iteration image, merges edit instruction via `PromptPipeline.merge_edit()`, processes through pipeline, runs img2img, creates new `Iteration`, persists to MongoDB
3. **List sessions** (`GET /sessions`): Returns all active sessions with `session_id`, `original_prompt`, `iteration_count`, `created_at`
4. **View session** (`GET /sessions/{id}`): Returns all iterations with metadata
5. **View iteration image** (`GET /sessions/{id}/image/{n}`): Returns the image for iteration *n*
6. **Resume session**: Frontend can switch to a different session via `handleResumeSession(sid)` — clears current state and loads the selected session
7. **End session** (`DELETE /sessions/{id}`): Promotes final iteration to gallery, saves/deletes from MongoDB

### Session Persistence

- Sessions are saved to MongoDB (`edit_sessions` collection) after each operation
- On startup (`_startup()`), previously persisted sessions are restored from MongoDB into memory
- On shutdown (`_shutdown()`), all active sessions are promoted to gallery and flushed to MongoDB

### Frontend UI

The Generate page shows:
- **History sidebar**: Lists active edit sessions (purple "session" badge) above completed jobs (with thumbnail previews)
- **Iteration timeline**: horizontal strip of clickable thumbnails (one per iteration)
- **Selected image**: large preview of the clicked iteration
- **Edit form**: text input for edit instructions + strength slider (0.05–0.95)
- **End Session button**: closes the session and promotes the result to the gallery
- **Stats**: iteration count and base prompt

---

## 6. Job Polling & Image Retrieval

After submission, the frontend polls for completion:

```
Frontend (2s interval)                   Backend
    │                                      │
    │  GET /jobs/{job_id}                  │
    │ ────────────────────────────────────► │
    │ ◄── { state: "running", ... }        │
    │                                      │
    │  GET /jobs/{job_id}                  │
    │ ────────────────────────────────────► │
    │ ◄── { state: "completed", ... }      │
    │                                      │
    │  GET /jobs/{job_id}/image            │
    │ ────────────────────────────────────► │
    │ ◄── image/png (best image bytes)     │
    │                                      │
    │  Create Blob URL, display in <img>   │
    ▼                                      ▼
```

1. **Poll loop** (`Generate.jsx`): Every 2 seconds, calls `GET /jobs/{job_id}` until `state` is `completed` or `failed`
2. **Image fetch** (`useEffect`): When state becomes `completed`, calls `GET /jobs/{job_id}/image`
3. **Display:** Response bytes are turned into a `Blob URL` via `URL.createObjectURL()` and rendered in an `<img>` tag
4. **Cleanup:** Previous Blob URLs are revoked on unmount or when a new image replaces them

---

## 7. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           FRONTEND                                  │
│  Landing → Login/Register → Generate Page                           │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────────────┐  │
│  │  Auth     │    │  Submit  │    │  Poll + Display              │  │
│  │  Context  │    │  Prompt  │    │  job status → fetch image    │  │
│  └────┬─────┘    └────┬─────┘    └────────────┬─────────────────┘  │
│       │               │                        │                    │
└───────┼───────────────┼────────────────────────┼────────────────────┘
        │               │                        │
   /auth/*         /generate              /jobs/* & /jobs/*/image
        │               │                        │
┌───────┼───────────────┼────────────────────────┼────────────────────┐
│       ▼               ▼                        ▼     BACKEND        │
│  ┌─────────┐    ┌───────────┐           ┌───────────┐              │
│  │  Auth   │    │ POST      │           │ GET       │              │
│  │  Router │    │ /generate │           │ /jobs/*   │              │
│  └────┬────┘    └─────┬─────┘           └─────┬─────┘              │
│       │               │                       │                     │
│       ▼               ▼                       ▼                     │
│  ┌─────────┐    ┌───────────┐           ┌───────────┐              │
│  │  User   │    │  Orch-    │◄──────────│  Job      │              │
│  │  Store  │    │  estrator │           │  Lookup   │              │
│  └────┬────┘    └─────┬─────┘           └───────────┘              │
│       │               │  (background task)                          │
│       │               ▼                                             │
│       │         ┌───────────────────────────────────┐              │
│       │         │       AdaptiveSampler              │              │
│       │         │  ┌─────────────┐                   │              │
│       │         │  │ Prompt      │ Stage 1: Spelling │              │
│       │         │  │ Pipeline    │ Stage 2: Grammar  │              │
│       │         │  │             │ Stage 3: Enhance  │              │
│       │         │  └──────┬──────┘                   │              │
│       │         │         ▼                          │              │
│       │         │  ┌─────────────┐  ┌────────────┐  │              │
│       │         │  │ Model       │  │ Quality    │  │              │
│       │         │  │ Manager     │  │ Evaluator  │  │              │
│       │         │  │ (SD 1.5)    │  │(CLIP+sharp)│  │              │
│       │         │  └──────┬──────┘  └─────┬──────┘  │              │
│       │         │         │  feedback loop │         │              │
│       │         │         └───────────────┘         │              │
│       │         └──────────────┬────────────────────┘              │
│       │                        ▼                                    │
│       │                  ┌───────────┐                              │
│       │                  │ Artifact  │                              │
│       │                  │ Store     │                              │
│       │                  └─────┬─────┘                              │
│       │                        │                                    │
└───────┼────────────────────────┼────────────────────────────────────┘
        │                        │
        ▼                        ▼
   ┌─────────────────────────────────┐
   │           MongoDB                │
   │  ┌───────┐ ┌──────┐ ┌────────┐  │
   │  │ users │ │ jobs │ │artifacts│  │
   │  └───────┘ └──────┘ └────────┘  │
   └─────────────────────────────────┘
```

---

## 8. Component Interaction Map

| Component | Depends On | Provides |
|-----------|-----------|----------|
| `main.py` | All engines, `db/connection`, `api/app` | Configured FastAPI `app` instance |
| `api/app.py` | Orchestrator, AdaptiveSampler, ArtifactStore, Auth | REST endpoints |
| `auth/router.py` | `auth/security`, `auth/store`, `auth/models` | Register / Login / Me endpoints |
| `auth/security.py` | bcrypt, PyJWT | Password hashing, JWT create/decode |
| `auth/store.py` | pymongo, `auth/models` | CRUD operations on `users` collection |
| `auth/dependencies.py` | `auth/security` | `get_current_user` FastAPI dependency |
| `orchestrator/orchestrator.py` | `core/models`, asyncio | Job queue, GPU lock, job lifecycle |
| `engines/prompt_pipeline.py` | symspellpy, transformers (Flan-T5) | Spelling + grammar + enhancement |
| `engines/adaptive_sampler.py` | ModelManager, QualityEvaluator, PromptPipeline | Feedback-driven generation loop |
| `engines/model_manager.py` | diffusers, torch | SD 1.5 pipeline load + generate + img2img |
| `engines/quality_evaluator.py` | transformers (CLIP), OpenCV, numpy, PIL | Image quality scoring |
| `engines/iterative_generator.py` | ModelManager, PromptPipeline (optional) | Iterative img2img editing API |
| `store/artifact_store.py` | pymongo, PIL | Image + metadata persistence |
| `db/connection.py` | pymongo, motor | Singleton MongoDB clients |
| `core/models.py` | stdlib only | `Job`, `AttemptRecord`, `Iteration`, `EditSession`, `JobState` dataclasses |

---

## 9. Error Handling

| Scenario | Where Caught | Recovery |
|----------|-------------|----------|
| Invalid/expired JWT | `auth/dependencies.py` | 401 Unauthorized |
| Duplicate email/username | `auth/router.py` | 409 Conflict |
| GPU model not loaded | `api/app.py` (guard) | 503 Service Unavailable |
| CUDA OOM during generation | `adaptive_sampler.py` | Clear cache, reduce steps, retry next attempt |
| All attempts fail (persistent OOM) | `adaptive_sampler.py` | `AssertionError` → job marked `FAILED` |
| Job not found | `api/app.py` | 404 Not Found |
| Artifact/image not found | `api/app.py` | 404 Not Found |
| Edit session not found | `api/app.py` | 404 Not Found |
| Edit on session with no image yet | `api/app.py` | 409 Conflict |
| MongoDB unreachable at startup | `main.py` | Fall back to in-memory stores |
| Unhandled exception in job | `orchestrator.py` | Job marked `FAILED`, error string persisted |

---

## 10. Deployment Topology

**Docker Compose** (`docker-compose.yml`) defines three services:

```
┌──────────────────────────────────────────────┐
│               Docker Host (GPU)              │
│                                              │
│  ┌──────────┐  ┌───────────┐  ┌───────────┐ │
│  │  nginx   │  │  FastAPI  │  │  MongoDB  │ │
│  │ frontend │─►│  backend  │─►│  mongo:7  │ │
│  │ :3000    │  │  :8000    │  │  :27017   │ │
│  │          │  │  (CUDA)   │  │           │ │
│  └──────────┘  └───────────┘  └───────────┘ │
│                      │                       │
│                ┌─────┴──────┐                │
│                │ HF model   │                │
│                │ cache vol  │                │
│                └────────────┘                │
└──────────────────────────────────────────────┘
```

| Service | Image / Build | Port | Notes |
|---------|--------------|------|-------|
| `mongo` | `mongo:7` | 27017 | Data stored in `mongo-data` volume; healthcheck via `mongosh` ping |
| `backend` | Build from `./Dockerfile` | 8000 | NVIDIA GPU passthrough; HF model cache volume; depends on healthy `mongo` |
| `frontend` | Build from `./frontend/Dockerfile` | 3000 | Nginx serves the built React SPA; proxies `/api` to the backend |

**Volumes:**
- `mongo-data` — persistent MongoDB storage
- `hf-cache` — cached Hugging Face model weights (SD 1.5, CLIP, Flan-T5)

---

## 11. Architecture Decisions

### ADR-001: Adaptive Sampling Over Model Fine-Tuning

**Status:** Accepted

**Context:** Two approaches were considered for improving output quality — fine-tuning model weights (e.g. LoRA) vs. adaptive sampling with feedback-driven regeneration.

**Decision:** PixelForge implements adaptive sampling with quality feedback rather than model fine-tuning.

**Rationale:**
- Distortion is often a sampling instability issue, not a model weights issue
- Regeneration with parameter adjustment is computationally cheaper than fine-tuning
- No risk of catastrophic forgetting or overfitting
- Fully offline and dataset-independent
- Reversible and controllable — original model weights are never modified

**Trade-offs:**
- Limited ability to correct deep model biases
- Relies on heuristic quality scoring (CLIP + sharpness) rather than learned quality models

### ADR-002: Single GPU Worker Architecture

**Status:** Accepted

**Context:** Stable Diffusion is GPU-intensive and concurrent execution risks VRAM fragmentation, race conditions, and unpredictable latency.

**Decision:** Implement a single-worker FIFO job queue with a GPU mutex (`asyncio.Lock`).

**Rationale:**
- Ensures exclusive GPU access — no VRAM contention
- Predictable job lifecycle and latency
- Avoids memory fragmentation from interleaved generation
- Simplifies debugging and observability

**Trade-offs:**
- No parallel throughput — jobs are serialised
- Horizontal scaling requires architectural redesign (see roadmap Phase 3)

---

## 12. Design Principles

1. **Fully offline execution** — No external API calls, no cloud dependencies, no fine-tuning
2. **No ML imports in core domain layer** — `core/models.py` uses stdlib only; ML dependencies are isolated in `engines/`
3. **Single GPU exclusive access** — One job at a time via FIFO queue + async mutex
4. **Deterministic metadata logging** — Every attempt records seed, steps, CFG, score, and timing for reproducibility
5. **Modular ML execution layer** — ModelManager, QualityEvaluator, and AdaptiveSampler are independent, injectable components
6. **Configurable adaptive loop** — Quality threshold, max attempts, and scoring weights are all configurable
7. **Clear separation of concerns** — API layer never touches ML code directly; orchestrator manages lifecycle; engines handle generation

---

## 13. Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 18, Vite 5, Tailwind CSS 3 | Single-page application |
| **Routing** | React Router v6 | Client-side navigation, route guards |
| **API** | FastAPI, Uvicorn | Async REST API, background tasks |
| **Auth** | bcrypt, PyJWT (HS256) | Password hashing, JWT tokens (24h expiry) |
| **Validation** | Pydantic v2 | Request/response model validation |
| **ML — Generation** | Stable Diffusion 1.5 (`diffusers`), PyTorch | Text-to-image and image-to-image generation |
| **ML — Quality** | CLIP ViT-B/32 (`transformers`), OpenCV | Text-image alignment scoring, sharpness |
| **ML — Prompts** | SymSpell, Flan-T5-small (`transformers`) | Spelling correction, grammar correction |
| **Database** | MongoDB 7 (`pymongo`, `motor`) | Users, jobs, artifacts, sessions |
| **Containerisation** | Docker, Docker Compose | Multi-service deployment with GPU passthrough |
| **Reverse Proxy** | Nginx | Serve frontend SPA, proxy API requests |
| **Testing** | pytest, httpx | Backend unit and integration tests |
| `mongo` | `mongo:7` | 27017 | Persistent volume `mongo-data` |
| `backend` | Custom `Dockerfile` | 8000 | NVIDIA GPU required, HF cache volume |
| `frontend` | Custom `frontend/Dockerfile` | 3000 (nginx) | Vite build → nginx static serving, proxies `/api` to backend |

**Environment variables:**
- `PIXELFORGE_SKIP_LOAD` — skip ML model loading (for tests)
- `PIXELFORGE_JWT_SECRET` — JWT signing key (defaults to dev-only hash)
- `MONGO_URL` — MongoDB connection string (default: `mongodb://localhost:27017`)
- `MONGO_DB_NAME` — database name (default: `pixelforge`)
- `VITE_API_URL` — frontend API base URL (default: `/api`)
