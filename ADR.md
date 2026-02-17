# ADR-001: Adaptive Sampling Over Model Fine-Tuning

## Status
Accepted

## Context

PixelForge aims to reduce distortion and improve image quality in Stable Diffusion outputs.

Two approaches were considered:

1. Fine-tuning model weights (e.g., LoRA training)
2. Adaptive sampling with feedback-driven regeneration

Fine-tuning introduces:
- High computational cost
- Risk of overfitting
- Irreversible model changes
- Need for curated training datasets

Adaptive sampling:
- Adjusts inference parameters
- Maintains original model weights
- Is reversible and controllable
- Requires no additional training data

## Decision

PixelForge will implement adaptive sampling with quality feedback rather than model fine-tuning.

## Rationale

- Distortion is often a sampling instability issue.
- Regeneration with parameter adjustment is computationally cheaper.
- No risk of catastrophic forgetting.
- Fully offline and dataset-independent.
- Easier to maintain and debug.

## Consequences

Positive:
- Faster iteration
- No retraining pipeline required
- Stable and predictable system behavior

Negative:
- Limited ability to correct deep model biases
- Relies on heuristic quality scoring
# ADR-002: Single GPU Worker Architecture

## Status
Accepted

## Context

Stable Diffusion is GPU-intensive and can cause:
- VRAM fragmentation
- Race conditions
- Unpredictable latency

Parallel execution without control risks system instability.

## Decision

Implement a single-worker FIFO job queue with a GPU mutex.

## Rationale

- Ensures exclusive GPU access
- Predictable job lifecycle
- Avoids memory fragmentation
- Simplifies debugging

## Consequences

Positive:
- Stability
- Deterministic behavior
- Easier observability

Negative:
- Reduced parallel throughput
- Not horizontally scalable without redesign
