# PixelForge Implemented Components

This file summarizes what is currently implemented in the repository.

## Backend Entry and Wiring

### main.py

- logging setup
- conditional model/pipeline load based on PIXELFORGE_SKIP_LOAD
- MongoDB connectivity check
- FastAPI app creation with create_app

### api/app.py

Implemented route groups:

- auth routes mounted from auth/router.py
- generation routes
  - POST /generate
  - GET /jobs
  - GET /jobs/{job_id}
  - GET /jobs/{job_id}/image
- artifact routes
  - GET /artifacts/{artifact_id}
  - GET /artifacts/{artifact_id}/meta
- iterative session routes
  - POST /generate-session
  - POST /edit
  - GET /sessions
  - GET /sessions/{session_id}
  - GET /sessions/{session_id}/image/{iteration}
  - DELETE /sessions/{session_id}

Supporting behavior:

- background job execution
- MongoDB startup/shutdown lifecycle hooks
- session restore/persist logic
- fallback in-memory mode

## Auth Layer

### auth/security.py

- bcrypt password hashing and verification
- JWT create/decode (HS256)

### auth/router.py

- POST /auth/register
- POST /auth/login
- GET /auth/me
- duplicate username/email checks

### auth/dependencies.py

- bearer token extraction and validation for protected routes

## Core Domain Models

### core/models.py

- JobState enum
- AttemptRecord dataclass
- Iteration dataclass
- EditSession dataclass
- Job dataclass with lifecycle helpers and serialization

## Engine Layer

### engines/model_manager.py

- Stable Diffusion 1.5 load and inference
- txt2img generation
- img2img generation
- CUDA OOM handling with cache cleanup
- attention/vae slicing and optional xformers enablement

### engines/prompt_pipeline.py

- spelling correction (SymSpell)
- grammar correction (Flan-T5)
- prompt enhancement and negative prompt synthesis
- edit prompt merge helper

### engines/quality_evaluator.py

- CLIP text-image alignment scoring
- sharpness scoring (Laplacian variance)
- weighted quality computation

### engines/adaptive_sampler.py

- bounded retry loop
- parameter adjustment strategy
- OOM-aware continuation behavior
- best attempt tracking and return bundle

### engines/iterative_generator.py

- initial session generation
- iterative img2img edit generation
- prompt merge fallback path

## Orchestration Layer

### orchestrator/orchestrator.py

- FIFO queue
- async GPU lock
- job submit/get/list/cancel lifecycle operations
- optional MongoDB persistence

## Storage Layer

### store/artifact_store.py

- InMemoryArtifactStore
- MongoArtifactStore
- image save/retrieve
- metadata save/retrieve
- session save/load/delete

### db/connection.py

- sync and async Mongo client factories
- connectivity checks
- index creation
- client cleanup

## Frontend Layer

### frontend/src/api.js

- auth APIs
- generation APIs
- session APIs
- image fetch helpers

### frontend/src/App.jsx and context

- guest/protected route handling
- auth state provider and token persistence

### frontend/src/pages/Generate.jsx

- generation form and polling
- job history with lazy thumbnails
- session creation and resume flow
- iterative edit timeline and strength controls
- session end and gallery promotion trigger

## Tests

Implemented backend tests in tests/:

- test_core_models.py
- test_adaptive_sampler.py
- test_quality_evaluator.py
- test_orchestrator.py
- test_artifact_store.py
- test_api.py
