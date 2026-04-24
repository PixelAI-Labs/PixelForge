# PixelForge Unimplemented and Deferred Items

This document tracks known gaps and planned follow-up work.

## 1. Face-Aware Quality Metric

Status: deferred

Current behavior:

- QualityEvaluator keeps face contribution at 0.0 (weight default is 0.0).

Planned work:

- add real face-quality scoring path
- enable optional weighting in combined score

## 2. Frontend Automated Testing

Status: not started

Current behavior:

- frontend testing is manual.

Planned work:

- add component/unit tests
- add end-to-end flow tests

## 3. Distributed and Multi-GPU Execution

Status: deferred

Current behavior:

- one active generation job per process using a single lock.

Planned work:

- persistent queue backend
- worker sharding and multi-GPU scheduling

## 4. Public Readability of Some Image Routes

Status: design decision pending

Current behavior:

- some image retrieval/session image endpoints do not require auth.

Planned work:

- review intended access policy
- tighten endpoint guards if user-scoped access is required

## 5. Artifact Metadata Endpoint Semantics

Status: partial

Current behavior:

- /artifacts/{artifact_id}/meta performs lookup through job-level metadata key path.

Planned work:

- provide explicit artifact-id-to-job mapping metadata endpoint
- document response shape as stable contract

## 6. UI Cleanup: Unused Helper

Status: low priority

Current behavior:

- Generate page retains bestArtifact helper stub that is not part of active rendering path.

Planned work:

- remove dead helper or implement direct usage path

## 7. Benchmark Automation

Status: not started

Current behavior:

- no built-in benchmark harness for latency/quality regression.

Planned work:

- add repeatable benchmark prompt suite
- emit summary metrics for CI trend tracking

## 8. Product Backlog Snapshot

- quality profile presets (speed/balanced/quality)
- artifact/gallery pagination and filters
- session comparison and side-by-side iteration diffing
- optional cloud/object storage backends
