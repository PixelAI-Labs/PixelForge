# PixelForge

Adaptive offline AI image generation using Stable Diffusion 1.5, automatic quality scoring, and feedback-driven parameter tuning.

PixelForge runs locally on NVIDIA GPU hardware, exposes a FastAPI backend, and includes a React frontend for generation and iterative image editing sessions.

## Highlights

- Adaptive regeneration loop (up to 10 attempts) that tunes steps, CFG scale, seed, and negative prompt when quality is low.
- Quality scoring with CLIP text-image alignment plus Laplacian sharpness.
- Prompt preprocessing pipeline: SymSpell spelling correction, Flan-T5 grammar correction, and rule-based prompt enhancement.
- Iterative img2img editing sessions with timeline playback and resume/end flow.
- JWT authentication (register, login, profile).
- MongoDB persistence with automatic in-memory fallback when MongoDB is unavailable.
- Docker Compose deployment for backend, frontend, and MongoDB.

## Architecture

```text
Frontend (React + Vite)
        |
        v
API (FastAPI + JWT auth)
        |
        v
Orchestrator (FIFO queue + GPU lock)
        |
        v
Generation Engine
  - ModelManager (SD 1.5 txt2img + img2img)
  - AdaptiveSampler
  - QualityEvaluator
  - PromptPipeline
        |
        v
Stores (MongoDB or in-memory)
```

## Tech Stack

- Backend: FastAPI, Pydantic, PyJWT, bcrypt
- ML: diffusers, transformers, torch (CUDA), accelerate
- Data: MongoDB (pymongo + motor)
- Frontend: React, React Router, Vite, Tailwind CSS
- Infra: Docker, Docker Compose, Nginx

## Requirements

- Python 3.10+
- Node.js 18+
- NVIDIA GPU with CUDA support (required for real image generation)
- MongoDB 7+ (optional)

## Quick Start (Local Development)

### 1) Clone and set up backend

```bash
git clone https://github.com/PixelAI-Labs/PixelForge.git
cd PixelForge
python -m venv .venv
```

Activate the virtual environment:

```powershell
# Windows
.venv\Scripts\activate
```

```bash
# Linux / macOS
source .venv/bin/activate
```

Install backend dependencies:

```bash
pip install -r requirements.txt
```

### 2) Run backend API

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Notes:

- On first run, model assets are downloaded (Stable Diffusion 1.5, CLIP, and grammar model on first prompt-pipeline use).
- If MongoDB is unreachable, PixelForge automatically starts with in-memory stores.

### 3) Run frontend (dev)

```bash
cd frontend
npm install
npm run dev
```

Frontend development server runs on http://localhost:3000.
In dev mode, /api/* is proxied to http://localhost:8000/*.

## Docker Compose

```bash
docker compose up --build
```

Services:

- Frontend (Nginx): http://localhost:3000
- Backend (FastAPI): http://localhost:8000
- MongoDB: localhost:27017

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `PIXELFORGE_SKIP_LOAD` | `0` | Set to `1` to skip model loading (primarily for tests). |
| `PIXELFORGE_JWT_SECRET` | deterministic dev hash | JWT signing secret (replace in production). |
| `MONGO_URL` | `mongodb://localhost:27017` | MongoDB connection URI. |
| `MONGO_DB_NAME` | `pixelforge` | MongoDB database name. |
| `VITE_API_URL` | `/api` | Frontend API base URL (mainly production/container config). |

## API Overview

### Auth

| Method | Endpoint | Auth Required | Description |
|---|---|---|---|
| POST | `/auth/register` | No | Register user and return JWT. |
| POST | `/auth/login` | No | Login and return JWT. |
| GET | `/auth/me` | Yes | Get current user profile. |

### Generation Jobs

| Method | Endpoint | Auth Required | Description |
|---|---|---|---|
| POST | `/generate` | Yes | Submit a text-to-image generation job. |
| GET | `/jobs` | No | List jobs. |
| GET | `/jobs/{job_id}` | No | Get job status/details. |
| GET | `/jobs/{job_id}/image` | No | Get best image for a completed job. |
| GET | `/artifacts/{artifact_id}` | No | Get image bytes by artifact ID. |
| GET | `/artifacts/{artifact_id}/meta` | No | Get job-level metadata (lookup currently keyed by job ID value). |

### Iterative Sessions

| Method | Endpoint | Auth Required | Description |
|---|---|---|---|
| POST | `/generate-session` | Yes | Start a new edit session (creates iteration 0). |
| POST | `/edit` | Yes | Apply img2img edit instruction to latest session image. |
| GET | `/sessions` | Yes | List active sessions. |
| GET | `/sessions/{session_id}` | Yes | Get full session details and iterations. |
| GET | `/sessions/{session_id}/image/{iteration}` | No | Get image for a specific iteration. |
| DELETE | `/sessions/{session_id}` | Yes | End session and promote final result to gallery/jobs. |

## Adaptive Sampling Behavior

Default runtime behavior in the app:

- Quality threshold: `0.65`
- Max attempts: `10`
- Initial defaults: `steps=30`, `guidance_scale=7.5`, `size=512x512`
- Per retry adjustment:
  - Steps: `+10` (capped at `100`)
  - CFG: `x1.1` (capped at `20.0`)
  - Seed: randomized
  - Negative prompt: strengthened for artifact suppression

## Testing

Run backend tests without loading GPU models:

```powershell
# Windows
$env:PIXELFORGE_SKIP_LOAD="1"
python -m pytest tests -v
```

```bash
# Linux / macOS
PIXELFORGE_SKIP_LOAD=1 python -m pytest tests -v
```

Current status:

- Backend test suite is present in tests/.
- Frontend has no automated test suite yet.

## Repository Structure

```text
api/            FastAPI routes and app factory
auth/           JWT auth, user model/store, dependencies
core/           Domain models (jobs, attempts, sessions)
db/             MongoDB connection and index setup
engines/        Model manager, adaptive sampler, evaluator, prompt pipeline
orchestrator/   Job queue and GPU mutex orchestration
store/          Artifact/session storage (in-memory + MongoDB)
frontend/       React app, Vite config, Nginx container config
tests/          Backend tests
```

## Project Documentation

- [IMPLEMENTED.md](IMPLEMENTED.md)
- [UNIMPLEMENTED.md](UNIMPLEMENTED.md)
- [WORKFLOW.md](WORKFLOW.md)
- [DESIGN.md](DESIGN.md)
- [API.md](API.md)
- [Deployment.md](Deployment.md)
- [Performance_Analysis.md](Performance_Analysis.md)
- [Test.md](Test.md)
- [Rodmap.md](Rodmap.md)
- [ADR.md](ADR.md)
- [Evalution.md](Evalution.md)

## License

This project is for educational and research purposes.
