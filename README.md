# PixelForge

**Adaptive offline AI image generation powered by Stable Diffusion 1.5.**

PixelForge automatically evaluates generated images and intelligently adjusts sampling parameters to reduce distortion and improve quality — no manual tuning required.

> Improve sampling intelligence, not model weights.

---

## Features

- **Adaptive regeneration loop** — automatically retries with tuned parameters (steps, CFG, seed, negative prompt) when quality falls below threshold (up to 10 attempts)
- **Quality scoring** — combined CLIP text-image alignment + Laplacian sharpness, normalised to 0–1
- **Prompt preprocessing** — three-stage pipeline: SymSpell spelling correction → Flan-T5 grammar correction → rule-based diffusion-friendly enhancement
- **Iterative editing sessions** — generate an initial image, then apply successive img2img edits (e.g. "add neon lights", "make it nighttime") with adjustable strength
- **JWT authentication** — secure user registration, login, and protected endpoints with bcrypt + HS256 JWTs
- **Fully offline** — no external APIs, no cloud dependencies, no fine-tuning
- **GPU-optimised** — CUDA float16 inference with attention slicing, VAE slicing, and optional xformers
- **REST API** — FastAPI backend with async job queue, background tasks, and PNG artifact retrieval
- **React frontend** — single-page application with generation studio, iterative editing UI, job history sidebar, and responsive design
- **Docker deployment** — three-service Docker Compose setup (backend + frontend + MongoDB) with GPU passthrough
- **Deterministic metadata** — every attempt logged with seed, steps, CFG, score, and generation time

---

## Architecture

```
┌──────────────────────────┐
│     React Frontend       │
│     (Vite + Tailwind)    │
└──────────────┬───────────┘
               │ HTTP
               ▼
┌──────────────────────────┐
│        FastAPI API        │
│   (Auth + Jobs + Sessions)│
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
│  ├── PromptPipeline       │
│  ├── ModelManager (SD 1.5)│
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

| Layer | Module | Responsibility |
|---|---|---|
| **Frontend** | `frontend/` | React SPA — prompt input, generation studio, iterative editing, job history |
| **API** | `api/` | HTTP endpoints, request validation, background task dispatch, auth |
| **Auth** | `auth/` | JWT authentication, bcrypt password hashing, user management |
| **Orchestrator** | `orchestrator/` | FIFO job queue, GPU mutual exclusion, lifecycle tracking |
| **Engines** | `engines/` | ML execution — prompt preprocessing, model loading, generation, quality evaluation, adaptive loop |
| **Core** | `core/` | Domain models (`Job`, `AttemptRecord`, `EditSession`, `JobState`) — no ML imports |
| **Store** | `store/` | Image and metadata persistence (MongoDB + in-memory) |
| **DB** | `db/` | MongoDB connection management, index creation |

---

## Requirements

- Python 3.10+
- Node.js 18+ (for frontend development)
- NVIDIA GPU with CUDA 11+ and 8 GB+ VRAM
- CUDA-capable PyTorch installation
- MongoDB 7+ (optional — falls back to in-memory stores)

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

### 3. Run the backend

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

On first launch the Stable Diffusion 1.5, CLIP, and Flan-T5 models are downloaded and loaded into GPU memory. Subsequent restarts reuse the cached model files.

### 4. Run the frontend (development)

```bash
cd frontend
npm install
npm run dev
```

The React app starts on `http://localhost:5173` and proxies API requests to `http://localhost:8000`.

### 5. Docker Compose (production)

```bash
docker compose up --build
```

This starts three services:
- **MongoDB** on port 27017
- **FastAPI backend** on port 8000 (with NVIDIA GPU passthrough)
- **Nginx frontend** on port 3000

---

## API Endpoints

### Authentication

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/auth/register` | Register a new user (username, email, password) | No |
| POST | `/auth/login` | Login with email + password, returns JWT | No |
| GET | `/auth/me` | Get current user profile | Yes |

### Image Generation

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/generate` | Submit a generation job (prompt, optional seed, optional negative_prompt) | Yes |
| GET | `/jobs` | List all submitted jobs | No |
| GET | `/jobs/{job_id}` | Get status of a specific job | No |
| GET | `/jobs/{job_id}/image` | Get the best image for a completed job (PNG) | No |
| GET | `/artifacts/{artifact_id}` | Download a stored image by artifact ID (PNG) | No |
| GET | `/artifacts/{artifact_id}/meta` | Get attempt metadata for an artifact | No |

### Iterative Editing Sessions

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/generate-session` | Create a new editing session (generates initial image) | Yes |
| POST | `/edit` | Apply an edit to the latest iteration (session_id, edit_instruction, strength) | Yes |
| GET | `/sessions` | List all active editing sessions | Yes |
| GET | `/sessions/{session_id}` | Get full session with all iterations | Yes |
| GET | `/sessions/{session_id}/image/{iteration}` | Get image for a specific iteration (PNG) | No |
| DELETE | `/sessions/{session_id}` | End session and promote result to gallery | Yes |

### Example Usage

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "email": "demo@example.com", "password": "secret123"}'

# Generate (use the token from register/login response)
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"prompt": "A dragon flying over a neon city at night"}'

# Check status
curl http://localhost:8000/jobs/{job_id}

# Download the image
curl http://localhost:8000/jobs/{job_id}/image --output image.png
```

---

## Adaptive Sampling Loop

Each generation request passes through the adaptive sampler:

1. **Preprocess** the prompt through the PromptPipeline (spelling → grammar → enhancement)
2. **Generate** an image with current parameters via Stable Diffusion 1.5
3. **Score** quality using CLIP text-image alignment (50%) + Laplacian sharpness (50%)
4. If score >= threshold (default `0.80`) → **accept**
5. Otherwise **adjust and retry**:
   - Steps: +10 per retry (bounded to 100)
   - CFG scale: ×1.1 per retry (bounded to 20.0)
   - Seed: randomised
   - Negative prompt: strengthened with anti-artifact terms
6. Repeat up to **10 attempts**, then return the best-scoring image

---

## Project Structure

```
PixelForge/
├── main.py                        # Entry point — model loading + app creation
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Backend container
├── docker-compose.yml             # Multi-service deployment
├── api/
│   └── app.py                     # FastAPI routes and app factory
├── auth/
│   ├── router.py                  # Register / Login / Me endpoints
│   ├── security.py                # bcrypt + JWT helpers
│   ├── dependencies.py            # get_current_user dependency
│   ├── models.py                  # User dataclass
│   └── store.py                   # MongoDB user store
├── core/
│   └── models.py                  # Job, AttemptRecord, EditSession, JobState
├── engines/
│   ├── model_manager.py           # SD 1.5 pipeline (txt2img + img2img)
│   ├── quality_evaluator.py       # CLIP alignment + sharpness scoring
│   ├── adaptive_sampler.py        # Feedback-driven regeneration loop
│   ├── iterative_generator.py     # Session-based img2img editing
│   └── prompt_pipeline.py         # SymSpell + Flan-T5 + enhancement
├── orchestrator/
│   └── orchestrator.py            # FIFO job queue with GPU mutex
├── store/
│   └── artifact_store.py          # InMemory + MongoDB artifact storage
├── db/
│   └── connection.py              # MongoDB connection management
├── frontend/
│   ├── Dockerfile                 # Frontend container (Nginx)
│   ├── nginx.conf                 # Reverse proxy config
│   ├── package.json               # Node.js dependencies
│   └── src/
│       ├── api.js                 # API client (fetch wrapper)
│       ├── App.jsx                # Router + route guards
│       ├── main.jsx               # React bootstrap
│       ├── components/
│       │   └── Navbar.jsx         # Navigation bar
│       ├── context/
│       │   ├── AuthContext.jsx    # Auth state provider
│       │   └── useAuth.js         # Auth hook
│       └── pages/
│           ├── Landing.jsx        # Marketing homepage
│           ├── Login.jsx          # Login form
│           ├── Register.jsx       # Registration form
│           └── Generate.jsx       # Image generation + editing studio
├── tests/
│   ├── test_core_models.py        # Job state transitions, dataclass tests
│   ├── test_quality_evaluator.py  # CLIP + sharpness scoring
│   ├── test_adaptive_sampler.py   # Adaptive loop logic
│   ├── test_orchestrator.py       # Job queue + GPU mutex
│   ├── test_artifact_store.py     # Image + metadata persistence
│   ├── test_api.py                # End-to-end HTTP integration tests
│   └── _inmemory_user_store.py    # Test-only user store
├── IMPLEMENTED.md                 # Complete function reference
├── UNIMPLEMENTED.md               # Stubs, deferred features, roadmap
└── WORKFLOW.md                    # System workflow & architecture
```

---

## Testing

### Backend (pytest)

All tests run **without** GPU hardware — engine components are mocked via `PIXELFORGE_SKIP_LOAD=1`.

```bash
# Windows
set PIXELFORGE_SKIP_LOAD=1
python -m pytest tests/ -v

# Linux / macOS
PIXELFORGE_SKIP_LOAD=1 pytest tests/ -v
```

| Test File | Coverage |
|---|---|
| `test_core_models.py` | Job lifecycle, AttemptRecord, EditSession serialisation |
| `test_quality_evaluator.py` | CLIP scoring, sharpness metric, weighted combination |
| `test_adaptive_sampler.py` | Parameter adjustments, retry loop, best-attempt selection |
| `test_orchestrator.py` | FIFO ordering, GPU mutex, concurrent jobs |
| `test_artifact_store.py` | In-memory + MongoDB image and metadata persistence |
| `test_api.py` | Full HTTP integration — auth, generation, sessions, error responses |

### Frontend

Manual testing performed — no automated test suite yet. See [UNIMPLEMENTED.md](UNIMPLEMENTED.md) for planned additions.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PIXELFORGE_SKIP_LOAD` | `0` | Skip model loading at startup (for testing) |
| `PIXELFORGE_JWT_SECRET` | dev-only SHA-256 hash | JWT signing secret (change in production) |
| `MONGO_URL` | `mongodb://localhost:27017` | MongoDB connection URI |
| `MONGO_DB_NAME` | `pixelforge` | MongoDB database name |

---

## GPU Memory Management

- Float16 inference reduces VRAM usage by ~50%
- Attention slicing and VAE slicing enabled automatically
- xformers memory-efficient attention enabled when available
- `torch.cuda.empty_cache()` called after every generation attempt
- CUDA OOM errors are caught gracefully — the adaptive sampler retries with reduced parameters

---

## Documentation

| Document | Description |
|----------|-------------|
| [IMPLEMENTED.md](IMPLEMENTED.md) | Complete function-level reference for every implemented symbol |
| [UNIMPLEMENTED.md](UNIMPLEMENTED.md) | Stubs, deferred features, and development roadmap |
| [WORKFLOW.md](WORKFLOW.md) | End-to-end system workflow, architecture decisions, design principles, deployment topology |

---

## License

This project is for educational and research purposes.
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