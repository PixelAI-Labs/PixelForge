# PixelForge Performance Analysis

This document captures current performance characteristics and a repeatable profiling plan.

## 1. Scope

Analyzed areas:

- generation latency
- adaptive retry overhead
- queue throughput behavior
- storage and retrieval path

## 2. Runtime Characteristics (By Design)

- Single active generation job per process due to GPU lock.
- Up to 10 attempts per job in worst-case quality scenarios.
- Additional retry attempts increase end-to-end latency linearly.
- Prompt pipeline grammar stage may add startup/first-use overhead.
- Artifact persistence adds I/O cost per attempt.

## 3. Key Bottlenecks

1. Diffusion inference time in ModelManager.generate/img2img.
2. CLIP scoring overhead in QualityEvaluator when enabled.
3. First-use model warmup and weight download latency.
4. Queue wait time under concurrent user submissions.

## 4. Reliability-Performance Trade-Offs

- FIFO + mutex improves stability and OOM safety but caps throughput.
- Quality retries improve output quality but can extend response time.
- In-memory mode removes DB overhead but sacrifices durability.

## 5. Suggested Profiling Method

### Backend Profiling

- Enable info-level logs.
- Capture per-attempt generation_time from metadata.
- Record job completion time versus attempt count.
- Compare prompt sets at fixed threshold values.

### Queue Profiling

- Submit N concurrent jobs.
- Track queue wait and run durations per job.
- Evaluate fairness and tail latency.

### API Retrieval Profiling

- Measure /jobs/{id}/image response latency for hot and cold DB cache states.

## 6. Recommended Metrics Dashboard

Track these metrics over time:

- avg_attempts_per_job
- p50/p95 job completion time
- generation failure rate
- OOM retry count
- queue depth over time
- DB write latency for artifacts and metadata

## 7. Optimization Priorities

1. Add benchmark script for repeatable latency baselines.
2. Add frontend and API pagination for large histories.
3. Add optional distributed queue and worker scaling path.
4. Introduce configurable retry policy per request class.
