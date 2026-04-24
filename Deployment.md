# PixelForge Deployment Guide

This guide covers local development and Docker Compose deployment.

## Prerequisites

- Python 3.10+
- Node.js 18+
- NVIDIA GPU with CUDA support (required for actual generation)
- Docker + Docker Compose (for container deployment)

## Local Development

### 1) Backend setup

```bash
python -m venv .venv
```

Activate environment:

```powershell
# Windows
.venv\Scripts\activate
```

```bash
# Linux / macOS
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start backend:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2) Frontend setup

```bash
cd frontend
npm install
npm run dev
```

- Frontend URL: http://localhost:3000
- API proxy in dev: /api -> http://localhost:8000

## Docker Compose Deployment

From repository root:

```bash
docker compose up --build
```

Services started:

- frontend (nginx): http://localhost:3000
- backend (FastAPI): http://localhost:8000
- mongo: mongodb://localhost:27017

## Environment Variables

Backend:

- PIXELFORGE_SKIP_LOAD
  - Default: 0
  - 1 skips model load (useful for tests)
- PIXELFORGE_JWT_SECRET
  - JWT signing secret
- MONGO_URL
  - Default: mongodb://localhost:27017
- MONGO_DB_NAME
  - Default: pixelforge

Frontend:

- VITE_API_URL
  - Default: /api

## Persistence and Caches

- MongoDB data volume: mongo-data
- HuggingFace model cache volume: hf-cache

## Operational Notes

- First startup may take longer due to model downloads.
- If MongoDB is unavailable in local mode, app falls back to in-memory persistence.
- Generation endpoints return 503 when model is not loaded or GPU is unavailable.

## Quick Health Checks

- Backend docs: http://localhost:8000/docs
- Backend jobs endpoint: GET http://localhost:8000/jobs
- Frontend shell: http://localhost:3000
