# PixelForge Roadmap

## Phase 1: Core Platform (Completed)

- [x] Stable Diffusion 1.5 integration
- [x] Adaptive retry loop with bounded parameter tuning
- [x] CLIP + sharpness quality scoring
- [x] JWT auth and protected generation endpoints
- [x] React generation UI with history panel
- [x] Iterative session editing workflow
- [x] Docker Compose deployment (frontend/backend/mongo)

## Phase 2: Quality Intelligence (In Progress)

- [ ] Face-aware quality scoring implementation
- [ ] Distortion classifier exploration
- [ ] Better per-attempt quality diagnostics in APIs/UI
- [ ] Prompt-quality benchmark suite for regressions

## Phase 3: Scalability and Reliability

- [ ] Persistent/distributed job queue backend
- [ ] Multi-GPU worker scheduling model
- [ ] Artifact storage abstraction for object stores
- [ ] API pagination for large histories

## Phase 4: Product Experience

- [ ] Frontend automated testing and CI checks
- [ ] User-level history filters and favorites
- [ ] Session compare view for iteration deltas
- [ ] Optional quality profile presets (speed/balanced/quality)
