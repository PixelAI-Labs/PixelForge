# PixelForge

**Adaptive offline AI image generation powered by Stable Diffusion 1.5.**

PixelForge automatically evaluates generated images and intelligently adjusts sampling parameters to reduce distortion and improve quality — no manual tuning required.

> Improve sampling intelligence, not model weights.

---

## Features

- **Adaptive regeneration loop** — automatically retries with tuned parameters (steps, CFG, seed, negative prompt) when quality falls below threshold (max 3 attempts)
- **Quality scoring** — combined CLIP text-image alignment + Laplacian sharpness, normalised to 0–1
- **Fully offline** — no external APIs, no cloud dependencies, no fine-tuning
- **GPU-optimised** — CUDA float16 inference with attention slicing, VAE slicing, and optional xformers
- **GPU-only** — requires an NVIDIA GPU with CUDA; no CPU fallback
- **REST API** — FastAPI backend with async job queue and PNG artifact retrieval
- **Deterministic metadata** — every attempt logged with seed, steps, CFG, score, and generation time

---

## Architecture

```
┌──────────────────────────┐
│        FastAPI API        │
│   POST /generate          │
│   GET  /jobs, /artifacts  │
└──────────────┬───────────┘
               │
               ▼
┌──────────────────────────┐
│     Job Orchestrator      │
│   FIFO queue + GPU mutex  │
└──────────────┬───────────┘
               │
               ▼
┌──────────────────────────┐
│    Generation Engine      │
│  ├── ModelManager         │
│  ├── QualityEvaluator     │
│  └── AdaptiveSampler      │
└──────────────┬───────────┘
               │
               ▼
┌──────────────────────────┐
│     Artifact Store        │
│   (In-Memory / MongoDB)   │
└──────────────────────────┘
```

| Layer | Responsibility |
|---|---|
| **API** (`api/`) | HTTP endpoints, request validation, background task dispatch |
| **Orchestrator** (`orchestrator/`) | FIFO job queue, GPU mutual exclusion, lifecycle tracking |
| **Engines** (`engines/`) | ML execution — model loading, generation, quality evaluation, adaptive loop |
| **Core** (`core/`) | Domain models (`Job`, `AttemptRecord`, `JobState`) — no ML imports |
| **Store** (`store/`) | Image and metadata persistence |

---

## Requirements

- Python 3.10+
- NVIDIA GPU with CUDA 11+ and 8 GB+ VRAM
- CUDA-capable PyTorch installation

---

## Quick Start

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/HM18042005/PixelForge.git
cd PixelForge
python -m venv .venv
```

Activate the environment:

```powershell
# Windows
.venv\Scripts\activate
```

```bash
# Linux / macOS
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** For CUDA support, ensure you install the appropriate PyTorch build for your CUDA version.
> See [pytorch.org/get-started](https://pytorch.org/get-started/locally/) for details.

### 3. Run the server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

On first launch the Stable Diffusion 1.5 and CLIP models are downloaded and loaded into GPU memory. Subsequent restarts reuse the cached model files.

---

## API Usage

### Generate an image

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "A portrait of a woman in soft lighting"}'
```

Response:

```json
{ "job_id": "abc123..." }
```

### Check job status

```bash
curl http://localhost:8000/jobs/{job_id}
```

Response:

```json
{
  "job_id": "abc123...",
  "status": "completed",
  "attempts": 2,
  "best_score": 0.78,
  "error": null
}
```

### Retrieve the image (PNG)

```bash
curl http://localhost:8000/artifacts/{artifact_id} --output image.png
```

### Retrieve attempt metadata

```bash
curl http://localhost:8000/artifacts/{artifact_id}/meta
```

Response:

```json
{
  "prompt": "A portrait of a woman in soft lighting",
  "attempts": [
    { "attempt": 1, "seed": 42, "steps": 30, "guidance_scale": 7.5, "quality_score": 0.61, "generation_time": 4.2 },
    { "attempt": 2, "seed": 314, "steps": 40, "guidance_scale": 8.25, "quality_score": 0.78, "generation_time": 5.1 }
  ],
  "selected_attempt": 2
}
```

---

## Adaptive Sampling Loop

Each generation request passes through the adaptive sampler:

1. Generate image with current parameters
2. Score quality (CLIP alignment + sharpness)
3. If score >= threshold (default `0.65`) → accept
4. Otherwise adjust and retry:
   - **Steps:** +10 per retry (bounded to 100)
   - **CFG scale:** ×1.1 per retry (bounded to 20.0)
   - **Seed:** randomised
   - **Negative prompt:** strengthened with default anti-artifact terms
5. Repeat up to 3 attempts, then return the best-scoring image

Debug logging prints every attempt with score, parameters, and timing.

---

## Project Structure

```
PixelForge/
├── main.py                    # Entry point — model loading + app creation
├── requirements.txt
├── api/
│   └── app.py                 # FastAPI routes and app factory
├── core/
│   └── models.py              # Domain models (Job, AttemptRecord, JobState)
├── engines/
│   ├── model_manager.py       # Stable Diffusion pipeline (load once, generate)
│   ├── adaptive_sampler.py    # Feedback-driven regeneration loop
│   └── quality_evaluator.py   # CLIP + sharpness scoring
├── orchestrator/
│   └── orchestrator.py        # FIFO job queue with GPU mutex
├── store/
│   └── artifact_store.py      # In-memory image + metadata persistence
└── tests/
    ├── test_adaptive_sampler.py
    ├── test_api.py
    ├── test_artifact_store.py
    ├── test_core_models.py
    ├── test_orchestrator.py
    └── test_quality_evaluator.py
```

---

## Running Tests

Tests are designed to run **without** ML dependencies — all engine components are mocked.

```bash
pip install pytest httpx pytest-asyncio
python -m pytest tests/ -v
```

To skip model loading during test imports:

```bash
set PIXELFORGE_SKIP_LOAD=1      # Windows
export PIXELFORGE_SKIP_LOAD=1   # Linux / macOS
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PIXELFORGE_SKIP_LOAD` | `0` | Set to `1` to skip model loading at startup (for testing) |

---

## GPU Memory Management

- Attention slicing and VAE slicing are enabled automatically to reduce VRAM usage
- xformers memory-efficient attention is enabled when available
- `torch.cuda.empty_cache()` is called after every generation attempt
- CUDA OOM errors are caught, cached memory is freed, and the adaptive loop continues with reduced steps

---

## Documentation

| Document | Description |
|---|---|
| [PRD.md](PRD.md) | Product Requirements Document |
| [DESIGN.md](DESIGN.md) | System design and component architecture |
| [API.md](API.md) | API endpoint specification |
| [Deployment.md](Deployment.md) | Deployment and setup guide |
| [Performance_Analysis.md](Performance_Analysis.md) | Performance benchmarks and analysis |
| [Test.md](Test.md) | Testing strategy |
| [Rodmap.md](Rodmap.md) | Project roadmap |
| [ADR.md](ADR.md) | Architecture Decision Records |
| [Evalution.md](Evalution.md) | Evaluation methodology |

---

## License

This project is for educational and research purposes.