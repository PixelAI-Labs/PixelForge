# 📘 PixelForge Design Document

## Adaptive Offline Image Generation System

---

# 1. System Vision

PixelForge is a fully offline AI image generation system built on Stable Diffusion 1.5.

The system improves output quality using a feedback-driven adaptive inference loop instead of fine-tuning or weight modification.

Core philosophy:

> Improve sampling intelligence, not model weights.

The system treats diffusion as a stochastic search process and uses measurable quality signals to guide exploration of latent space.

---

# 2. System Architecture Overview

```
┌──────────────────────────┐
│        Frontend          │
│     (React + Vite)       │
└──────────────┬───────────┘
               │ HTTP
               ▼
┌──────────────────────────┐
│        FastAPI API       │
│   (Authentication + Jobs)│
└──────────────┬───────────┘
               │
               ▼
┌──────────────────────────┐
│     Job Orchestrator     │
│   (FIFO + GPU Mutex)     │
└──────────────┬───────────┘
               │
               ▼
┌──────────────────────────┐
│     Generation Engine    │
│                          │
│  ├── ModelManager        │
│  ├── QualityEvaluator    │
│  └── AdaptiveSampler     │
└──────────────┬───────────┘
               │
               ▼
┌──────────────────────────┐
│      Artifact Store      │
│ (MongoDB / In-Memory)    │
└──────────────────────────┘
```

---

# 3. Architectural Principles

* Fully offline execution
* No ML imports in core domain layer
* Single GPU exclusive access
* Deterministic metadata logging
* Modular ML execution layer
* Configurable adaptive loop
* Clear separation of concerns

---

# 4. Component Design

---

## 4.1 Frontend Layer (React + Vite)

### Responsibilities:

* Prompt input interface
* Display generation progress
* Show attempt history and quality scores
* Display final selected image
* Authentication UI
* Gallery browsing

### Design Notes:

* Stateless UI
* Communicates only through REST API
* No direct ML logic

---

## 4.2 API Layer (FastAPI)

### Responsibilities:

* Accept generation requests
* Manage authentication (JWT)
* Expose job status endpoints
* Serve artifacts
* Serve quality metadata

### Endpoints:

* POST `/generate`
* GET `/jobs`
* GET `/jobs/{id}`
* GET `/artifacts/{id}`
* GET `/artifacts/{id}/meta`

### Design Constraints:

* Non-blocking request handling
* Return job ID immediately
* Poll-based job status

---

## 4.3 Job Orchestrator

### Purpose:

Manage safe and controlled GPU execution.

### Responsibilities:

* FIFO queue
* Single GPU lock (mutex)
* Job lifecycle tracking:

  * Pending
  * Running
  * Completed
  * Failed
  * Cancelled
* Cooperative cancellation support

### Design Rationale:

Diffusion models are GPU-intensive and not safe for concurrent execution without control.

---

## 4.4 Generation Engine

This is the core intelligence layer.

It consists of three subcomponents.

---

### 4.4.1 ModelManager

#### Responsibilities:

* Load Stable Diffusion 1.5 once at startup
* Manage device placement
* Expose configurable generation interface

#### Design Constraints:

* Use `dtype=torch.float16`
* Load model once
* No reloading during jobs
* Parameterized inference call

#### Interface Example:

```
generate(prompt, steps, guidance_scale, seed, width, height)
```

---

### 4.4.2 QualityEvaluator

#### Purpose:

Quantitatively measure image quality.

#### Metrics:

1. CLIP Alignment

   * Extract image & text embeddings via CLIP ViT-B/32
   * L2-normalise both vectors
   * True cosine similarity, remapped [-1, 1] → [0, 1]
   * Graceful fallback to sharpness-only if CLIP unavailable

2. Face Detection Score

   * Detect face presence
   * Confidence scoring
   * *(Placeholder — not yet active, weight = 0)*

4. Sharpness Score

   * Laplacian variance (OpenCV)

#### Combined Score:

```
quality_score =
    w1 * alignment +
    w2 * face_score +
    w3 * sharpness
```

Normalized between 0 and 1.

#### Design Goals:

* Lightweight (<200ms overhead)
* Deterministic
* Extensible

---

### 4.4.3 AdaptiveSampler

#### Purpose:

Adjust inference parameters based on feedback.

#### Algorithm:

1. Generate initial image
2. Evaluate quality
3. If score ≥ threshold → accept
4. Else:

   * Increase steps (bounded)
   * Adjust CFG slightly
   * Change seed
   * Strengthen negative prompt
5. Regenerate
6. Repeat up to max 10 attempts
7. Select best-scoring image

#### Constraints:

* Max 10 attempts
* Quality threshold: 0.80
* Small parameter deltas (steps +10, CFG ×1.1)
* Keep best attempt
* CUDA OOM handling: clear cache, reduce steps, continue

#### Rationale:

Sampling variability is stochastic. Many distortions can be corrected via re-sampling without modifying model weights.

---

## 4.5 Artifact Store

### Responsibilities:

* Persist images
* Persist attempt metadata
* Track quality scores
* Provide retrieval

### Storage Options:

* MongoDB (primary)
* In-memory fallback

### Metadata Stored:

* Prompt
* Seed per attempt
* Steps per attempt
* CFG per attempt
* Quality score per attempt
* Selected attempt
* Execution time

---

# 5. Data Flow

1. User submits prompt.
2. API creates job.
3. Job enters FIFO queue.
4. Orchestrator acquires GPU lock.
5. Initial image generated.
6. Quality evaluated.
7. Adaptive loop executed if needed.
8. Best result stored.
9. Job marked completed.
10. Frontend retrieves result.

---

# 6. Technology Stack

---

## 6.1 Machine Learning

| Technology     | Purpose                           | Justification                    |
| -------------- | --------------------------------- | -------------------------------- |
| PyTorch        | Core tensor engine                | Industry standard, GPU optimized |
| Diffusers      | Stable Diffusion implementation   | Modular, maintained              |
| Transformers   | CLIP + Flan-T5                    | Alignment scoring, grammar correction |
| OpenCV         | Sharpness detection               | Efficient image processing       |
| SymSpellPy     | Spelling correction               | Fast compound word correction    |
| Mediapipe      | Face detection (planned)          | Lightweight and reliable         |

---

## 6.2 Backend

| Technology | Purpose          | Justification                 |
| ---------- | ---------------- | ----------------------------- |
| FastAPI    | REST API         | Async, high performance       |
| Uvicorn    | ASGI server      | Lightweight production server |
| PyJWT      | Authentication   | Stateless JWT handling        |
| bcrypt     | Password hashing | Secure hashing                |

---

## 6.3 Frontend

| Technology   | Purpose          | Justification      |
| ------------ | ---------------- | ------------------ |
| React        | UI framework     | Declarative UI     |
| Vite         | Build tool       | Fast HMR, modern bundling |
| Tailwind CSS | Styling          | Rapid development  |

---

## 6.4 Persistence

| Technology      | Purpose          | Justification                |
| --------------- | ---------------- | ---------------------------- |
| MongoDB         | Artifact storage | Flexible document storage    |
| In-memory store | Fallback         | Resilience if DB unavailable |

---

# 7. Performance Design

* GPU-only generation recommended
* Max 10 regeneration attempts (threshold 0.80)
* No model reload inside loop
* CLIP + sharpness scoring under 200ms
* Img2img editing uses shared pipeline weights (no extra VRAM)
* Single-worker execution

---

# 8. Observability

Each generation attempt logs:

* Seed
* Steps
* CFG
* Resolution
* Quality score
* Generation time
* Total attempts

Structured logging recommended.

---

# 9. Scalability Considerations

Future extensibility:

* Multi-GPU worker pool
* Distributed job queue
* Persistent job recovery
* Learned quality predictor
* Reinforcement-style sampling policy

---

# 10. Design Philosophy

PixelForge does not modify model weights.

It improves the exploration strategy of latent space.

Instead of treating diffusion as a one-shot generator,
it treats it as a controllable stochastic search process.

This preserves model stability while improving output reliability.

```

---

Now step back and notice something important.

Your project has evolved from:

“Local Stable Diffusion app”

into

“Closed-loop generative control system.”

That is a much stronger conceptual foundation.

The interesting future question is not “can it generate?”

It’s:

Which signals best predict distortion, and how should sampling policy respond?

That’s where engineering becomes research.
```
