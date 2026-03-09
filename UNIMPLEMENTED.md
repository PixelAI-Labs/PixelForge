# PixelForge — Unimplemented Functions & Future Roadmap

This document lists every function or feature in the PixelForge codebase that is **not yet fully implemented** — i.e. stubs, placeholders, or deferred logic — and outlines the planned roadmap for future development.

For all implemented functions, see [IMPLEMENTED.md](IMPLEMENTED.md).  
For the end-to-end system workflow, see [WORKFLOW.md](WORKFLOW.md).

---

## 1. `bestArtifact(job)` — Frontend artifact lookup

| Detail | Value |
|--------|-------|
| **File** | `frontend/src/pages/Generate.jsx` |
| **Line** | 110 |
| **Current body** | `return null;` |

### What it should do

Given a completed job object (which contains a `best_attempt` field), this function should resolve and return the artifact key/URL for the best image so it can be rendered inline in the job history sidebar.

### Why it's still a stub

The developer comment reads:

> *"job object from listJobs has best_attempt; we need the artifact key. In a full implementation you'd look this up; for now show via /artifacts endpoint."*

### Current workaround (functional)

Job history thumbnails now work **without** this function. The `Generate.jsx` component uses `fetchJobImage(jobId)` to lazily fetch each completed job's best image as a blob URL and caches results in the `jobThumbs` state (keyed by `job_id`). A `useEffect` iterates over completed jobs and populates thumbnails via `fetchedThumbsRef` to avoid redundant fetches.

The `bestArtifact()` stub still returns `null` but is no longer called in the rendering path — thumbnails are rendered from `jobThumbs[job.job_id]` instead.

### Remaining action

- This function can be safely removed or implemented for completeness, but it is **no longer blocking** thumbnail display.

---

## 2. Face Detection Scoring — Quality Evaluator

| Detail | Value |
|--------|-------|
| **File** | `engines/quality_evaluator.py` |
| **Line** | 160 |
| **Current body** | `face = 0.0  # Face detection kept at weight 0 by default` |

### What it should do

According to the module docstring and `DESIGN.md`, the quality scoring formula is:

```
combined score = w_clip * clip + w_face * face + w_sharpness * sharpness
```

The **face detection** component should use **MediaPipe** (or an equivalent library) to compute a face-detection confidence score when the generated image contains faces. This metric helps the adaptive sampler prefer outputs where faces are well-formed.

### Why it's unimplemented

The `w_face` weight defaults to `0.0` in the constructor and the evaluation method hard-codes `face = 0.0` instead of calling any detection model. The feature was deferred — the evaluator works with only CLIP alignment and sharpness today.

### What needs to happen

1. Add a `face_score(image)` method to `QualityEvaluator` that:
   - Runs MediaPipe Face Detection (or similar) on the image.
   - Returns a confidence score normalised to `[0, 1]`.
2. Call `face_score()` inside `evaluate()` when `self._w_face > 0`.
3. Expose the `w_face` weight so users/config can enable face-aware scoring.

---

## 3. `ArtifactStoreProtocol` — Protocol Interface (by design)

| Detail | Value |
|--------|-------|
| **File** | `store/artifact_store.py` |
| **Lines** | 27–31 |
| **Current body** | `...` (Ellipsis) on all 5 methods |

### Methods

| Method | Signature |
|--------|-----------|
| `save_image` | `(self, image: Image.Image, job_id: str, attempt: int) -> str` |
| `get_image_bytes` | `(self, artifact_id: str) -> Optional[bytes]` |
| `get_best_image_bytes` | `(self, job_id: str) -> Optional[bytes]` |
| `save_metadata` | `(self, job_id: str, prompt: str, attempts: List[AttemptRecord], selected: int) -> None` |
| `get_metadata` | `(self, job_id: str) -> Optional[Dict[str, Any]]` |

### Context

This is a **Python `Protocol`** (PEP 544). The `...` body is idiomatic and intentional — it defines the contract that all artifact store implementations must satisfy. Two concrete implementations already exist and are fully implemented:

- `InMemoryArtifactStore` (for tests)
- `MongoArtifactStore` (for production)

> **No action required** unless a new storage backend is needed (e.g., S3, GCS), in which case a new class implementing these 5 methods should be added.

---

## Summary

| # | Function / Feature | File | Severity | Action Required |
|---|--------------------|------|----------|-----------------|
| 1 | `bestArtifact(job)` | `frontend/src/pages/Generate.jsx:110` | Low | Stub still returns `null` but thumbnails work via `fetchJobImage()` + `jobThumbs` state. Can be removed or implemented for completeness. |
| 2 | Face detection scoring | `engines/quality_evaluator.py:114` | Low | Add MediaPipe-based `face_score()` method and wire it into `evaluate()` |
| 3 | `ArtifactStoreProtocol` | `store/artifact_store.py:27-31` | None | Idiomatic Protocol stubs — only needed if adding a new storage backend |

---

## Roadmap

### Phase 1 — Core System (Completed)
- [x] Stable Diffusion 1.5 integration
- [x] Adaptive regeneration loop (up to 10 attempts)
- [x] CLIP alignment + Laplacian sharpness quality metrics
- [x] FastAPI REST API with JWT authentication
- [x] FIFO job queue with GPU mutex
- [x] MongoDB artifact persistence
- [x] React frontend with iterative editing sessions
- [x] Prompt preprocessing pipeline (SymSpell + Flan-T5 + enhancement)
- [x] Docker Compose deployment (backend + frontend + MongoDB)

### Phase 2 — Quality Intelligence
- [ ] Learned distortion classifier (lightweight CNN for artifact detection)
- [ ] Adaptive CFG prediction (predict optimal CFG from prompt semantics)
- [ ] Face detection scoring (MediaPipe integration — see item #2 above)
- [ ] Advanced logging dashboard (real-time job metrics, GPU utilisation)

### Phase 3 — Scaling
- [ ] Multi-GPU worker pool (replace single mutex with distributed scheduling)
- [ ] Reinforcement-style sampling policy (trained parameter selection)
- [ ] Redis / RabbitMQ job queue (persistent, distributed)
- [ ] S3 / GCS artifact storage (replace MongoDB for images)

### Phase 4 — Personalisation
- [ ] User preference modelling (learn per-user style preferences from feedback)
- [ ] Intelligent parameter prediction (predict steps, seed, resolution from prompt)
- [ ] Prompt history and favourites
- [ ] Image gallery pagination

### Scalability Improvements (Planned)
- [ ] Cloud deployment (AWS EC2 GPU / GCP / Azure NC-series with auto-scaling)
- [ ] Microservice decomposition (API gateway, job scheduler, generation worker, storage)
- [ ] CDN integration (CloudFront / Cloudflare for image delivery)
- [ ] Kubernetes orchestration (horizontal pod autoscaling, rolling updates)
