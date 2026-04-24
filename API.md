# PixelForge API Specification

Base URL (local):

- Backend direct: http://localhost:8000
- Frontend proxy path: /api

Authentication:

- JWT bearer tokens are returned by auth endpoints.
- Protected endpoints require header: Authorization: Bearer <token>

## Auth Endpoints

### POST /auth/register

Register a new user and return a JWT.

Request body:

```json
{
  "username": "demo",
  "email": "demo@example.com",
  "password": "secret123"
}
```

Success response (201):

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "user_id": "<uuid>",
  "username": "demo"
}
```

### POST /auth/login

Authenticate a user and return a JWT.

Request body:

```json
{
  "email": "demo@example.com",
  "password": "secret123"
}
```

Success response (200):

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "user_id": "<uuid>",
  "username": "demo"
}
```

### GET /auth/me

Return current user profile.

- Auth required: Yes

Success response (200):

```json
{
  "user_id": "<uuid>",
  "username": "demo",
  "email": "demo@example.com"
}
```

## Generation Endpoints

### POST /generate

Submit a generation job.

- Auth required: Yes

Request body:

```json
{
  "prompt": "A cinematic portrait of a woman in soft light",
  "seed": 42,
  "negative_prompt": "blurry, low quality"
}
```

Success response (200):

```json
{
  "job_id": "<uuid>"
}
```

### GET /jobs

List all jobs.

- Auth required: No

Success response (200):

```json
[
  {
    "job_id": "<uuid>",
    "prompt": "...",
    "state": "completed",
    "attempts": 2,
    "best_score": 0.7821,
    "best_attempt": 1,
    "created_at": 1714000000,
    "completed_at": 1714000015,
    "error": null
  }
]
```

### GET /jobs/{job_id}

Get status for one job.

- Auth required: No

Success response (200):

```json
{
  "job_id": "<uuid>",
  "state": "running",
  "prompt": "...",
  "attempts": 1,
  "best_score": 0.4512,
  "error": null
}
```

### GET /jobs/{job_id}/image

Get best PNG image for a completed job.

- Auth required: No
- Response content type: image/png

### GET /artifacts/{artifact_id}

Get PNG image by artifact id.

- Auth required: No
- Response content type: image/png

### GET /artifacts/{artifact_id}/meta

Get metadata document for an artifact lookup key.

- Auth required: No
- Response content type: application/json

Note:

- Current implementation looks up metadata using the path value as job-level key.

## Iterative Session Endpoints

### POST /generate-session

Create a new edit session and enqueue initial generation.

- Auth required: Yes

Request body:

```json
{
  "prompt": "A fantasy castle on a hill",
  "seed": null,
  "negative_prompt": ""
}
```

Success response (200):

```json
{
  "session_id": "<uuid>",
  "iteration": 0
}
```

### POST /edit

Apply an img2img edit instruction to the latest session iteration.

- Auth required: Yes

Request body:

```json
{
  "session_id": "<uuid>",
  "edit_instruction": "add neon lights",
  "strength": 0.35
}
```

Success response (200):

```json
{
  "session_id": "<uuid>",
  "iteration": 1
}
```

### GET /sessions

List active sessions.

- Auth required: Yes

Success response (200):

```json
[
  {
    "session_id": "<uuid>",
    "original_prompt": "A fantasy castle on a hill",
    "iteration_count": 2,
    "created_at": 1714000100
  }
]
```

### GET /sessions/{session_id}

Get full session object with iteration history.

- Auth required: Yes

### GET /sessions/{session_id}/image/{iteration}

Get PNG image for one session iteration.

- Auth required: No
- Response content type: image/png

### DELETE /sessions/{session_id}

End a session and promote final iteration to jobs/gallery.

- Auth required: Yes

Success response (200):

```json
{
  "status": "ended",
  "session_id": "<uuid>"
}
```

## Common Error Responses

- 401: invalid/expired token
- 403: missing auth for protected endpoint
- 404: job/session/artifact not found
- 409: invalid session state (for example, no image yet)
- 503: generation unavailable when model is not loaded
