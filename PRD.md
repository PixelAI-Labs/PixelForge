# PixelForge Product Requirements Document

## 1. Product Summary

PixelForge is an offline-first image generation platform built around Stable Diffusion 1.5, with automatic quality evaluation and adaptive regeneration.

Primary value:

- reduce manual prompt-parameter tuning
- improve quality consistency across generations
- provide secure authenticated workflows with iterative editing

## 2. Problem Statement

Raw diffusion output quality can vary heavily by seed and sampling settings. Users often need repeated manual tuning to avoid distortion or low-fidelity outputs.

PixelForge addresses this by automatically evaluating attempts and retrying with bounded parameter changes.

## 3. Target Users

- AI creators who run local GPU workflows
- developers and students learning inference orchestration
- privacy-focused users who avoid cloud generation tools

## 4. Product Goals

- deliver an end-to-end local generation workflow
- improve accepted image quality through adaptive retries
- support iterative editing sessions in a single UI
- persist artifacts and metadata for traceability

## 5. In-Scope Features

### Implemented

- JWT auth: register/login/me
- text-to-image job submission
- adaptive retry loop with quality scoring
- job status polling and best-image retrieval
- iterative edit sessions (create, edit, list, inspect, end)
- MongoDB persistence with fallback in-memory mode
- Docker Compose deployment

### Out of Scope (Current)

- fine-tuning and LoRA training workflows
- distributed multi-GPU scheduling
- face-specific quality metric in production path
- frontend automated test suite

## 6. Functional Requirements

1. user can register and authenticate with JWT.
2. authenticated user can submit generation request with prompt and optional seed/negative prompt.
3. system can retry generation up to configured max attempts.
4. system stores attempt metadata and selected result.
5. user can create and iterate image edit sessions.
6. user can end sessions and promote final result to gallery/jobs.

## 7. Non-Functional Requirements

- reliability:
  - graceful behavior with unavailable MongoDB
  - consistent job lifecycle transitions
- performance:
  - bounded retries
  - serialized GPU execution for memory safety
- security:
  - bcrypt password hashing
  - JWT bearer auth on protected endpoints
- maintainability:
  - modular engine components and clear API boundaries

## 8. Success Indicators

- lower manual re-run burden for common prompts
- stable generation pipeline under concurrent request load
- reproducible attempt-level metadata for analysis

## 9. Risks

- quality metrics may not fully capture visual defects
- single-GPU queue limits throughput
- missing frontend test automation increases regression risk

## 10. Next Product Milestones

- face-quality scoring integration
- richer artifact metadata APIs
- distributed queue and worker scaling options
- frontend automated test coverage
