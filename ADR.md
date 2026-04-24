# PixelForge Architecture Decision Records

This document tracks major architecture decisions for PixelForge.

## ADR-001: Adaptive Sampling Over Model Fine-Tuning

- Status: Accepted
- Date: 2026-04-24

### Context

PixelForge targets higher generation quality without training new model weights.
Two options were considered:

1. Fine-tune Stable Diffusion weights (LoRA/full fine-tuning)
2. Keep model weights fixed and adapt inference parameters per attempt

### Decision

PixelForge uses a feedback-driven adaptive sampler (steps, CFG, seed, negative prompt adjustments) instead of model fine-tuning.

### Consequences

- Positive:
  - No training dataset or training pipeline required
  - No catastrophic forgetting risk
  - Easier rollback and reproducibility
- Negative:
  - Improvement depends on quality heuristics
  - Does not directly fix deep model bias

## ADR-002: Single GPU Worker With FIFO Scheduling

- Status: Accepted
- Date: 2026-04-24

### Context

Concurrent diffusion runs on one GPU increase OOM risk and can cause unpredictable latency.

### Decision

PixelForge serializes generation with a FIFO orchestrator plus an async GPU lock.

### Consequences

- Positive:
  - Stable memory behavior and predictable lifecycle transitions
  - Simpler debugging and observability
- Negative:
  - Throughput is bounded by one active generation at a time

## ADR-003: MongoDB Persistence With Automatic In-Memory Fallback

- Status: Accepted
- Date: 2026-04-24

### Context

The application should run in development/test environments even if MongoDB is unavailable.

### Decision

On startup, PixelForge verifies MongoDB connectivity. If unavailable, it automatically switches to in-memory stores.

### Consequences

- Positive:
  - Local development remains unblocked
  - Test setup is simpler
- Negative:
  - In-memory data is not durable across restarts
  - Behavior differs from production persistence mode
