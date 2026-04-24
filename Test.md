# PixelForge Testing Guide

## 1. Test Scope

PixelForge test coverage currently focuses on backend correctness and API behavior.

### Covered Areas

- domain model lifecycle transitions
- adaptive sampler retry logic
- quality evaluator calculations
- orchestrator scheduling semantics
- artifact store persistence behavior
- auth and API endpoint integration

### Not Yet Automated

- frontend unit tests
- frontend e2e tests

## 2. Test Environment

Backend tests run without loading heavy models by setting:

- PIXELFORGE_SKIP_LOAD=1

This keeps tests deterministic and GPU-independent.

## 3. Run Commands

### Windows PowerShell

```powershell
$env:PIXELFORGE_SKIP_LOAD="1"
python -m pytest tests -v
```

### Linux/macOS

```bash
PIXELFORGE_SKIP_LOAD=1 python -m pytest tests -v
```

## 4. Test File Map

- tests/test_core_models.py
- tests/test_adaptive_sampler.py
- tests/test_quality_evaluator.py
- tests/test_orchestrator.py
- tests/test_artifact_store.py
- tests/test_api.py

## 5. Suggested Additions

1. frontend unit testing with React Testing Library.
2. end-to-end workflow tests (register -> generate -> edit -> end session).
3. benchmark/regression tests for attempt count and latency under fixed prompts.
4. contract tests for API response schema stability.

## 6. CI Recommendations

- run backend pytest suite on each PR
- enforce lint and type checks where configured
- add smoke test hitting /auth/register, /generate, /jobs/{id}
