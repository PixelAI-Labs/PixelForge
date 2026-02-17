# 📡 API Specification

## POST /generate

Request:
{
  "prompt": "A portrait of a woman in soft lighting"
}

Response:
{
  "job_id": "abc123"
}

---

## GET /jobs/{job_id}

Response:
{
  "status": "completed",
  "attempts": 2,
  "best_score": 0.78
}

---

## GET /artifacts/{id}

Returns:
- Image (PNG)

---

## GET /artifacts/{id}/meta

Returns:
{
  "prompt": "...",
  "attempts": [
    { "seed": 42, "score": 0.61 },
    { "seed": 314, "score": 0.78 }
  ],
  "selected_attempt": 2
}
