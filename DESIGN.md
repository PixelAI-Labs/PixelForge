# PixelForge System Design

## 1. Goal

PixelForge is an offline image generation system that improves output quality by adapting inference parameters at runtime instead of modifying model weights.

Core principle:

- Improve sampling behavior, not model weights.

## 2. Architecture

```text
React Frontend
   |
   v
FastAPI API (auth + jobs + sessions)
   |
   v
Orchestrator (FIFO queue + async GPU lock)
   |
   v
Generation Layer
  - PromptPipeline
  - ModelManager
  - QualityEvaluator
  - AdaptiveSampler
   |
   v
Artifact/User Stores (MongoDB or in-memory fallback)
```

## 3. Layer Responsibilities

### Frontend (frontend/src)

- Authentication UI and route guards
- Prompt submission
- Job polling and image rendering
- Iterative session editing UX

### API Layer (api/app.py)

- Endpoint validation and serialization
- Authentication enforcement on protected routes
- Background job dispatch
- Session lifecycle endpoints

### Orchestration Layer (orchestrator/orchestrator.py)

- FIFO scheduling
- Job lifecycle transitions
- Single active GPU execution lock
- Optional persistence to MongoDB jobs collection

### Generation Layer (engines)

- ModelManager: SD 1.5 txt2img/img2img pipelines and CUDA memory protections
- PromptPipeline: spelling, grammar, and quality prompt enrichment
- QualityEvaluator: CLIP alignment plus sharpness scoring
- AdaptiveSampler: retry loop with bounded parameter adjustments

### Persistence Layer (store, db, auth/store)

- User, artifact, metadata, and session persistence in MongoDB
- In-memory fallback mode for unavailable DB/test contexts

## 4. Adaptive Sampling Design

Each generation request can run up to 10 attempts.

Retry adjustments:

- steps: +10 (max 100)
- guidance scale: x1.1 (max 20.0)
- seed: regenerated
- negative prompt: strengthened

Threshold behavior:

- App factory default threshold is 0.65
- AdaptiveSampler class default is 0.80
- create_app currently passes 0.65 unless overridden

The best-scoring attempt is stored and exposed to clients.

## 5. Quality Evaluation Design

Implemented scoring components:

- CLIP text-image cosine alignment, remapped to [0, 1]
- Laplacian sharpness score, normalized to [0, 1]

Deferred component:

- face scoring placeholder remains weight 0.0

Combined score:

```text
score = (w_clip * clip + w_face * face + w_sharpness * sharpness) / total_weight
```

## 6. Session Editing Design

Iterative sessions keep a timeline of edits:

1. create session with initial txt2img output
2. apply edit instructions through img2img
3. persist each iteration artifact
4. end session to promote final image to jobs/gallery

## 7. Runtime and Reliability Decisions

- GPU-only generation path for production use
- OOM handling with cache clearing and retry logic
- MongoDB connectivity check at startup
- automatic in-memory fallback when MongoDB is unreachable

## 8. Security Design

- bcrypt password hashing
- JWT access token (HS256)
- protected generation/session endpoints via dependency injection

## 9. Known Trade-Offs

- Single-worker GPU lock favors stability over throughput
- No frontend automated test suite yet
- Session/image APIs are partially public by design (job/session image fetch endpoints)

## 10. Extension Points

- Add face scoring model
- Add persistent/distributed queue backend
- Add multi-GPU orchestration
- Add object storage backend for artifacts
