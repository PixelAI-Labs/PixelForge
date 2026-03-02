# Implemented Functions & Components

A complete reference of every implemented function, method, and component in the PixelForge codebase, grouped by module.

---

## Table of Contents

- [Backend (Python)](#backend-python)
  - [main.py — Application Entry Point](#mainpy--application-entry-point)
  - [api/app.py — FastAPI Application Factory & Routes](#apiapppy--fastapi-application-factory--routes)
  - [core/models.py — Domain Models](#coremodelspy--domain-models)
  - [engines/model_manager.py — Stable Diffusion Pipeline](#enginesmodel_managerpy--stable-diffusion-pipeline)
  - [engines/quality_evaluator.py — Image Quality Scoring](#enginesquality_evaluatorpy--image-quality-scoring)
  - [engines/prompt_pipeline.py — Prompt Preprocessing Pipeline](#enginesprompt_pipelinepy--prompt-preprocessing-pipeline)
  - [engines/adaptive_sampler.py — Feedback-Driven Regeneration](#enginesadaptive_samplerpy--feedback-driven-regeneration)
  - [orchestrator/orchestrator.py — Job Queue & GPU Mutex](#orchestratororchestratopy--job-queue--gpu-mutex)
  - [store/artifact_store.py — Image & Metadata Persistence](#storeartifact_storepy--image--metadata-persistence)
  - [db/connection.py — MongoDB Connection Manager](#dbconnectionpy--mongodb-connection-manager)
  - [auth/security.py — Password & JWT Helpers](#authsecuritypy--password--jwt-helpers)
  - [auth/dependencies.py — FastAPI Auth Dependencies](#authdependenciespy--fastapi-auth-dependencies)
  - [auth/models.py — User Model](#authmodelspy--user-model)
  - [auth/store.py — MongoDB User Store](#authstorepy--mongodb-user-store)
  - [auth/router.py — Auth Endpoints](#authrouterpy--auth-endpoints)
  - [tests/_inmemory_user_store.py — Test User Store](#tests_inmemory_user_storepy--test-user-store)
- [Frontend (React / JSX)](#frontend-react--jsx)
  - [src/api.js — API Client](#srcapijs--api-client)
  - [src/main.jsx — App Bootstrap](#srcmainjsx--app-bootstrap)
  - [src/App.jsx — Router & Route Guards](#srcappjsx--router--route-guards)
  - [src/context/AuthContext.jsx — Auth State Management](#srccontextauthcontextjsx--auth-state-management)
  - [src/components/Navbar.jsx — Navigation Bar](#srccomponentsnavbarjsx--navigation-bar)
  - [src/pages/Landing.jsx — Landing Page](#srcpageslandingjsx--landing-page)
  - [src/pages/Login.jsx — Login Page](#srcpagesloginjsx--login-page)
  - [src/pages/Register.jsx — Registration Page](#srcpagesregisterjsx--registration-page)
  - [src/pages/Generate.jsx — Image Generation Studio](#srcpagesgeneratejsx--image-generation-studio)

---

## Backend (Python)

### `main.py` — Application Entry Point

| Symbol | Type | What It Does |
|--------|------|-------------|
| Module-level code | Script | Configures logging, creates `ModelManager`, `QualityEvaluator`, and `PromptPipeline` instances, verifies the MongoDB connection, and builds the FastAPI `app` via `create_app()`. Respects `PIXELFORGE_SKIP_LOAD` env var to defer GPU model loading and disable the prompt pipeline during tests. |

---

### `api/app.py` — FastAPI Application Factory & Routes

| Symbol | Type | What It Does |
|--------|------|-------------|
| `GenerateRequest` | Pydantic Model | Validates incoming generation requests (`prompt`, optional `seed`, optional `negative_prompt`). |
| `GenerateResponse` | Pydantic Model | Returns the `job_id` of a submitted generation job. |
| `JobStatusResponse` | Pydantic Model | Returns job status fields: `job_id`, `status`, `attempts`, `best_score`, `error`. |
| `create_app(model_manager, quality_evaluator, prompt_pipeline, quality_threshold, use_memory)` | Factory Function | Builds and configures the FastAPI application. Sets up CORS, selects MongoDB or in-memory stores, initialises the user store, creates the `AdaptiveSampler` (with optional `PromptPipeline`) and `Orchestrator`, registers all route handlers, and wires up startup/shutdown lifecycle events. |
| `_execute_job(job)` | Inner Function | Blocking callback passed to the orchestrator. Runs the adaptive sampler, persists each generated image via the artifact store, saves attempt metadata, and updates the `Job` model with results. |
| `POST /generate` | Route | Accepts a `GenerateRequest`, creates a `Job`, submits it to the orchestrator, and schedules execution as a FastAPI background task. Returns the `job_id`. Requires JWT auth. Returns 503 if no GPU model is loaded. |
| `GET /jobs` | Route | Returns a list of all submitted jobs (as dicts) from the orchestrator. |
| `GET /jobs/{job_id}` | Route | Returns the status of a single job. Returns 404 if not found. |
| `GET /artifacts/{artifact_id}` | Route | Serves a stored PNG image by its artifact ID. Returns 404 if not found. |
| `GET /jobs/{job_id}/image` | Route | Returns the best generated image for a completed job as a PNG response. Returns 404 if no image is found. |
| `GET /artifacts/{artifact_id}/meta` | Route | Returns the attempt metadata document for a given artifact/job ID. Returns 404 if not found. |
| `_startup()` | Lifecycle Event | (MongoDB mode) Pings MongoDB and creates required indexes on app startup. |
| `_shutdown()` | Lifecycle Event | (MongoDB mode) Gracefully closes MongoDB clients on app shutdown. |

---

### `core/models.py` — Domain Models

| Symbol | Type | What It Does |
|--------|------|-------------|
| `JobState` | Enum | Defines job lifecycle states: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`. |
| `AttemptRecord` | Dataclass | Stores metadata for a single generation attempt: `attempt_number`, `seed`, `steps`, `guidance_scale`, `width`, `height`, `quality_score`, `generation_time`, `image_key`. |
| `Job` | Dataclass | Represents a full generation job with prompt, parameters, lifecycle state, and list of attempts. |
| `Job.mark_running()` | Method | Transitions job state to `RUNNING`. |
| `Job.mark_completed(best_attempt)` | Method | Transitions job state to `COMPLETED`, records the best attempt index and completion timestamp. |
| `Job.mark_failed(error)` | Method | Transitions job state to `FAILED`, stores the error message and completion timestamp. |
| `Job.mark_cancelled()` | Method | Transitions job state to `CANCELLED` and records the completion timestamp. |
| `Job.add_attempt(record)` | Method | Appends an `AttemptRecord` to the job's attempt list. |
| `Job.best_score()` | Method | Returns the highest `quality_score` across all attempts (0.0 if none). |
| `Job.to_dict()` | Method | Serialises the job to a plain dict for API responses (includes `job_id`, `prompt`, `state`, `attempts` count, `best_score`, `best_attempt`, timestamps, `error`). |

---

### `engines/model_manager.py` — Stable Diffusion Pipeline

| Symbol | Type | What It Does |
|--------|------|-------------|
| `ModelManager.__init__(model_id, device, auto_load)` | Constructor | Stores config and optionally loads the Stable Diffusion pipeline on creation. Defaults to `runwayml/stable-diffusion-v1-5`. |
| `ModelManager._resolve_device()` | Method | Resolves the compute device. Raises `RuntimeError` if no CUDA GPU is detected. |
| `ModelManager.load()` | Method | Downloads and loads the Stable Diffusion 1.5 pipeline in float16, moves it to GPU, disables the safety checker, and enables memory optimisations (attention slicing, VAE slicing, xformers if available). No-op if already loaded. |
| `ModelManager.is_loaded` | Property | Returns `True` if the pipeline has been loaded. |
| `ModelManager.device` | Property | Exposes the device string (e.g. `"cuda"`) for GPU cleanup. |
| `ModelManager.generate(prompt, steps, guidance_scale, seed, width, height, negative_prompt)` | Method | Runs a single Stable Diffusion inference pass with the given parameters and returns the output as a `PIL.Image`. Handles CUDA OOM errors by clearing the cache and re-raising. Generates a random seed if none is provided. |

---

### `engines/quality_evaluator.py` — Image Quality Scoring

| Symbol | Type | What It Does |
|--------|------|-------------|
| `QualityEvaluator.__init__(w_clip, w_face, w_sharpness, device)` | Constructor | Stores scoring weights and device config. Defaults: 50% CLIP, 0% face, 50% sharpness. |
| `QualityEvaluator._resolve_device()` | Method | Selects CUDA if available; raises `RuntimeError` otherwise. |
| `QualityEvaluator.load()` | Method | Downloads and loads the CLIP ViT-B/32 model and processor from HuggingFace. Puts the model in eval mode on GPU. No-op if already loaded. Gracefully falls back to sharpness-only scoring (sets `w_clip=0`) if CLIP cannot be loaded (e.g. offline with no local cache). |
| `QualityEvaluator.clip_score(prompt, image)` | Method | Extracts image and text embeddings via CLIP's `vision_model`/`text_model` + projection layers, L2-normalises both, computes true cosine similarity (dot product of unit vectors), and remaps from [-1, 1] to [0, 1]. Returns 0.0 if CLIP is not loaded. |
| `QualityEvaluator.sharpness_score(image)` | Static Method | Converts the image to grayscale, computes the Laplacian variance, and normalises it to [0, 1] (capped at variance / 1000). |
| `QualityEvaluator.evaluate(prompt, image)` | Method | Computes the weighted combined score: `(w_clip * clip + w_face * face + w_sharpness * sharpness) / total_weight`, clamped to [0, 1]. |

---

### `engines/prompt_pipeline.py` — Prompt Preprocessing Pipeline

A three-stage pipeline that preprocesses user prompts before image generation: spelling correction → grammar correction → diffusion-friendly enhancement.

| Symbol | Type | What It Does |
|--------|------|-------------|
| `PromptPipeline.__init__(enabled, device)` | Constructor | Stores the enable flag and device (default `"cpu"`). Initialises a threading lock for lazy model loading. No models are loaded until first use. |
| `PromptPipeline.process(prompt)` | Method | Runs all three stages sequentially and returns `(enhanced_prompt, negative_prompt)`. When disabled, returns the original prompt with a default negative prompt unchanged. Logs the output of each stage. |
| `PromptPipeline._ensure_symspell()` | Method | Thread-safe lazy loader for the SymSpell dictionary. Uses double-checked locking to load the built-in English frequency dictionary exactly once. |
| `PromptPipeline._correct_spelling(text)` | Method | **Stage 1** — Applies SymSpell `lookup_compound` with max edit distance 2 to correct misspelled words across the full prompt. |
| `PromptPipeline._ensure_grammar_model()` | Method | Thread-safe lazy loader for the Flan-T5-small model and tokenizer from HuggingFace. Loads onto the configured device in eval mode exactly once. |
| `PromptPipeline._correct_grammar(text)` | Method | **Stage 2** — Sends the prompt to Flan-T5-small with the instruction `"Correct the grammar of this sentence: <text>"`. Uses deterministic generation (no sampling, max 128 new tokens). Returns the corrected text. |
| `PromptPipeline._enhance(text)` | Static Method | **Stage 3** — Rule-based enhancement. Prefixes short prompts (<8 words) with `"Highly detailed image of"`. Appends quality keywords (`cinematic lighting, ultra sharp focus, 4k resolution`) if none are already present. Returns the enhanced prompt and a default negative prompt (`"blurry, distorted, low resolution, extra limbs, malformed anatomy"`). |

---

### `engines/adaptive_sampler.py` — Feedback-Driven Regeneration

| Symbol | Type | What It Does |
|--------|------|-------------|
| `SamplingResult` | Dataclass | Holds the final output of an adaptive loop: `best_image`, `best_attempt` index, list of `AttemptRecord`s, and all generated images. |
| `_clear_cuda_cache()` | Module Function | Calls `torch.cuda.empty_cache()` if CUDA is available; silently skips if torch is not installed. |
| `AdaptiveSampler.__init__(model_manager, quality_evaluator, quality_threshold, max_attempts, prompt_pipeline)` | Constructor | Stores references to the `ModelManager`, `QualityEvaluator`, and optional `PromptPipeline`, along with the quality threshold (default 0.80) and max attempts (default 10). |
| `AdaptiveSampler.run(prompt, seed, steps, guidance_scale, width, height, negative_prompt)` | Method | If a `PromptPipeline` is attached, preprocesses the prompt through spelling correction, grammar correction, and diffusion-friendly enhancement before generation. Merges the pipeline's negative prompt with any user-supplied one. Then executes the adaptive sampling loop: generates an image, evaluates quality, and if below threshold, adjusts parameters (increases steps by 10, multiplies CFG by 1.1, changes seed, strengthens negative prompt) and retries up to `max_attempts` (10) times. Handles CUDA OOM gracefully by reducing steps. Clears GPU memory after each attempt. Logs original, corrected, and enhanced prompts. Returns a `SamplingResult` with the best image and all attempt records. |

---

### `orchestrator/orchestrator.py` — Job Queue & GPU Mutex

| Symbol | Type | What It Does |
|--------|------|-------------|
| `_job_to_doc(job)` | Module Function | Serialises a `Job` dataclass into a MongoDB-compatible dict document. |
| `_doc_to_job(doc)` | Module Function | Deserialises a MongoDB document back into a `Job` dataclass, including all nested `AttemptRecord`s. |
| `Orchestrator.__init__(db)` | Constructor | Initialises the FIFO job queue (OrderedDict), cancellation set, and optional MongoDB `jobs` collection. If a DB is provided, restores previously persisted jobs into memory on startup. |
| `Orchestrator._persist(job)` | Method | Upserts the job document to MongoDB (no-op if running in-memory). |
| `Orchestrator._get_lock()` | Method | Lazily creates an `asyncio.Lock` for GPU mutual exclusion. |
| `Orchestrator.submit(job)` | Method | Adds a job to the in-memory queue, persists it to MongoDB, and returns the job ID. |
| `Orchestrator.get_job(job_id)` | Method | Looks up and returns a job by ID, or `None`. |
| `Orchestrator.list_jobs()` | Method | Returns all jobs in submission order. |
| `Orchestrator.cancel(job_id)` | Method | Requests cooperative cancellation. Immediately cancels `PENDING` jobs; marks `RUNNING` jobs for cancellation. Returns `True` if cancellation was accepted. |
| `Orchestrator.is_cancelled(job_id)` | Method | Returns `True` if the given job ID has been flagged for cancellation. |
| `Orchestrator.run_job(job, execute_fn)` | Async Method | Acquires the GPU lock, transitions the job to `RUNNING`, calls `execute_fn` in a thread executor, and handles success/failure state transitions. Persists state after each transition. |

---

### `store/artifact_store.py` — Image & Metadata Persistence

#### `InMemoryArtifactStore` (for tests)

| Symbol | Type | What It Does |
|--------|------|-------------|
| `__init__()` | Constructor | Initialises in-memory dicts for images, metadata, and job-to-artifact mappings. |
| `save_image(image, job_id, attempt)` | Method | Encodes a PIL Image to PNG bytes, stores it in memory keyed by a random UUID, and tracks the artifact under the job ID. Returns the artifact ID. |
| `get_image_bytes(artifact_id)` | Method | Returns raw PNG bytes for a given artifact ID, or `None`. |
| `get_best_image_bytes(job_id)` | Method | Looks up the metadata for a job, finds the selected attempt's image, and returns its bytes. Falls back to the last stored artifact for the job. |
| `save_metadata(job_id, prompt, attempts, selected)` | Method | Stores a dict with the prompt, per-attempt details (seed, steps, CFG, score, time, image key), and the selected attempt index. |
| `get_metadata(job_id)` | Method | Returns the metadata dict for a job, or `None`. |

#### `MongoArtifactStore` (production)

| Symbol | Type | What It Does |
|--------|------|-------------|
| `__init__(db)` | Constructor | Gets handles to the `artifacts` and `artifact_meta` MongoDB collections. |
| `save_image(image, job_id, attempt)` | Method | Encodes a PIL Image to PNG, stores it as a BSON Binary document in the `artifacts` collection with `artifact_id`, `job_id`, and `attempt` fields. Returns the artifact ID. |
| `get_image_bytes(artifact_id)` | Method | Queries the `artifacts` collection and returns raw image bytes, or `None`. |
| `get_best_image_bytes(job_id)` | Method | Queries `artifact_meta` for the selected attempt, resolves its `image_key`, and returns the corresponding image bytes. Falls back to the most recent artifact for the job. |
| `save_metadata(job_id, prompt, attempts, selected)` | Method | Upserts a metadata document into `artifact_meta` with prompt, per-attempt details, and the selected attempt index. |
| `get_metadata(job_id)` | Method | Queries `artifact_meta` for the job and returns the document (excluding `_id`), or `None`. |

---

### `db/connection.py` — MongoDB Connection Manager

| Symbol | Type | What It Does |
|--------|------|-------------|
| `get_async_client()` | Function | Returns (or creates) a singleton Motor async MongoDB client. |
| `get_sync_client()` | Function | Returns (or creates) a singleton pymongo sync MongoDB client. |
| `get_async_db()` | Function | Returns the async database handle for `pixelforge`. |
| `get_sync_db()` | Function | Returns the sync database handle for `pixelforge`. |
| `ping_mongo()` | Async Function | Pings MongoDB via the async client; returns `True` if reachable, `False` otherwise. Logs success/failure. |
| `ensure_indexes()` | Async Function | Creates required unique and non-unique indexes on `users`, `jobs`, `artifacts`, and `artifact_meta` collections. Uses `_create_index_safe()` to handle duplicate keys and invalid specs gracefully. |
| `close_clients()` | Function | Gracefully closes both the async and sync MongoDB clients and resets them to `None`. |
| `verify_sync_connection()` | Function | Pings MongoDB via the sync client at startup; returns `True`/`False`. Used in `main.py` to decide between MongoDB and in-memory mode. |

---

### `auth/security.py` — Password & JWT Helpers

| Symbol | Type | What It Does |
|--------|------|-------------|
| `_default_secret()` | Function | Returns a deterministic SHA-256 dev-only JWT secret (warns: change in production). |
| `hash_password(password)` | Function | Returns a bcrypt hash of the plaintext password. |
| `verify_password(password, hashed)` | Function | Checks a plaintext password against its bcrypt hash; returns `True`/`False`. |
| `create_access_token(user_id, username)` | Function | Creates and signs a JWT containing `sub` (user ID), `username`, `iat`, and `exp` (24h). Uses HS256. |
| `decode_access_token(token)` | Function | Decodes and validates a JWT; returns the payload dict or `None` if expired/invalid. |

---

### `auth/dependencies.py` — FastAPI Auth Dependencies

| Symbol | Type | What It Does |
|--------|------|-------------|
| `get_current_user(credentials)` | Async Dependency | Extracts the JWT from the `Authorization: Bearer` header, decodes it via `decode_access_token()`, and returns the payload (user ID + username). Raises 401 if the token is invalid or expired. |

---

### `auth/models.py` — User Model

| Symbol | Type | What It Does |
|--------|------|-------------|
| `User` | Dataclass | Represents a registered user with fields: `username`, `email`, `hashed_password`, `user_id` (auto-generated UUID), `created_at` (timestamp), `is_active` (default `True`). |

---

### `auth/store.py` — MongoDB User Store

| Symbol | Type | What It Does |
|--------|------|-------------|
| `_user_to_doc(user)` | Function | Serialises a `User` dataclass to a MongoDB document dict (lowercases email). |
| `_doc_to_user(doc)` | Function | Deserialises a MongoDB document back to a `User` dataclass. |
| `UserStore.__init__(db)` | Constructor | Gets a handle to the `users` MongoDB collection. |
| `UserStore.add(user)` | Method | Inserts a new user document into the collection. |
| `UserStore.get_by_id(user_id)` | Method | Finds a user by `user_id`; returns `User` or `None`. |
| `UserStore.get_by_email(email)` | Method | Finds a user by email (case-insensitive); returns `User` or `None`. |
| `UserStore.get_by_username(username)` | Method | Finds a user by username (case-insensitive regex); returns `User` or `None`. |
| `UserStore.email_exists(email)` | Method | Returns `True` if the email is already registered. |
| `UserStore.username_exists(username)` | Method | Returns `True` if the username is already taken (case-insensitive). |

---

### `auth/router.py` — Auth Endpoints

| Symbol | Type | What It Does |
|--------|------|-------------|
| `init_user_store(store)` | Function | Injects the `UserStore` instance into the module-level variable. Must be called once during app startup. |
| `_store()` | Function | Returns the injected `UserStore`; raises `RuntimeError` if not initialised. |
| `RegisterRequest` | Pydantic Model | Validates registration input: `username` (3–30 chars), `email` (min 5 chars), `password` (min 6 chars). |
| `LoginRequest` | Pydantic Model | Validates login input: `email`, `password`. |
| `AuthResponse` | Pydantic Model | Returns `access_token`, `token_type`, `user_id`, `username` after successful auth. |
| `MeResponse` | Pydantic Model | Returns `user_id`, `username`, `email` for the current user. |
| `POST /auth/register` | Route | Validates uniqueness of email and username, hashes the password, creates a `User`, persists it, generates a JWT, and returns an `AuthResponse`. Returns 409 on conflict. |
| `POST /auth/login` | Route | Looks up the user by email, verifies the password, generates a JWT, and returns an `AuthResponse`. Returns 401 on invalid credentials. |
| `GET /auth/me` | Route | Decodes the JWT, looks up the user by ID, and returns a `MeResponse`. Returns 401 if the user no longer exists. |

---

### `tests/_inmemory_user_store.py` — Test User Store

| Symbol | Type | What It Does |
|--------|------|-------------|
| `InMemoryUserStore.__init__()` | Constructor | Initialises three in-memory dicts indexed by user ID, email, and username. |
| `InMemoryUserStore.add(user)` | Method | Stores the user in all three lookup dicts. |
| `InMemoryUserStore.get_by_id(user_id)` | Method | Returns the user by ID or `None`. |
| `InMemoryUserStore.get_by_email(email)` | Method | Returns the user by email (lowercased) or `None`. |
| `InMemoryUserStore.get_by_username(username)` | Method | Returns the user by username (lowercased) or `None`. |
| `InMemoryUserStore.email_exists(email)` | Method | Returns `True` if the email is in the store. |
| `InMemoryUserStore.username_exists(username)` | Method | Returns `True` if the username is in the store. |

---

## Frontend (React / JSX)

### `src/api.js` — API Client

| Symbol | Type | What It Does |
|--------|------|-------------|
| `authHeaders()` | Function | Reads the JWT from `localStorage` and returns an `Authorization: Bearer` header object (or empty). |
| `request(path, options)` | Function | Core fetch wrapper. Prepends the base URL, injects auth + JSON headers, handles error responses by throwing with the `detail` message, and parses JSON. |
| `register(username, email, password)` | Function | Sends `POST /auth/register` with credentials; returns the auth response. |
| `login(email, password)` | Function | Sends `POST /auth/login` with credentials; returns the auth response. |
| `getMe()` | Function | Sends `GET /auth/me`; returns the current user profile. |
| `generateImage(prompt, seed, negativePrompt)` | Function | Sends `POST /generate` with prompt parameters; returns `{ job_id }`. |
| `getJob(jobId)` | Function | Sends `GET /jobs/{jobId}`; returns the job status object. |
| `listJobs()` | Function | Sends `GET /jobs`; returns an array of all job objects. |
| `artifactUrl(artifactId)` | Function | Returns the full URL to download an artifact image by ID. |
| `jobImageUrl(jobId)` | Function | Returns the full URL to download the best image for a job. |
| `fetchJobImage(jobId)` | Function | Fetches the best image for a job as a blob with auth headers, creates a blob URL, and returns it. Throws on failure. |

---

### `src/main.jsx` — App Bootstrap

| Symbol | Type | What It Does |
|--------|------|-------------|
| Module-level code | Script | Mounts the React app into the DOM root element, wrapped in `StrictMode`, `BrowserRouter`, and `AuthProvider`. |

---

### `src/App.jsx` — Router & Route Guards

| Symbol | Type | What It Does |
|--------|------|-------------|
| `ProtectedRoute({ children })` | Component | Redirects unauthenticated users to `/login`; renders children if logged in. |
| `GuestRoute({ children })` | Component | Redirects authenticated users to `/generate`; renders children if not logged in. |
| `App()` | Component | Renders the `Navbar` and defines all routes: `/` (Landing), `/login` (guest-only), `/register` (guest-only), `/generate` (protected), `*` (redirect to `/`). |

---

### `src/context/AuthContext.jsx` — Auth State Management

| Symbol | Type | What It Does |
|--------|------|-------------|
| `AuthProvider({ children })` | Component | On mount, validates the stored JWT by calling `getMe()`. Provides `user`, `loginUser()`, and `logout()` to the context. Shows a loading spinner until the token check completes. |
| `loginUser(data)` | Context Function | Stores the JWT in `localStorage` and sets the user state with `user_id` and `username`. |
| `logout()` | Context Function | Removes the JWT from `localStorage` and clears the user state. |
| `useAuth()` | Hook | Returns the auth context (`user`, `loginUser`, `logout`). Throws if used outside `AuthProvider`. |

---

### `src/components/Navbar.jsx` — Navigation Bar

| Symbol | Type | What It Does |
|--------|------|-------------|
| `Navbar()` | Component | Renders a fixed-position glass navigation bar. Shows the PixelForge logo/link. When logged in: shows "Generate" link, username, and "Log out" button. When logged out: shows "Log in" and "Sign up" buttons. |

---

### `src/pages/Landing.jsx` — Landing Page

| Symbol | Type | What It Does |
|--------|------|-------------|
| `Landing()` | Component | Renders the marketing homepage with a hero section (headline, description, CTA buttons), a features grid (Adaptive Sampling, Quality Evaluation, GPU Orchestration), and a bottom CTA section. Adapts button text based on auth state. |

---

### `src/pages/Login.jsx` — Login Page

| Symbol | Type | What It Does |
|--------|------|-------------|
| `Login()` | Component | Renders a login form (email + password). On submit, calls the `login` API, stores the token via `loginUser()`, and navigates to `/generate`. Displays inline error messages on failure. |
| `handle(e)` | Inner Function | Updates form state from input change events. |
| `submit(e)` | Inner Function | Prevents default form submission, calls the login API, handles success/error. |

---

### `src/pages/Register.jsx` — Registration Page

| Symbol | Type | What It Does |
|--------|------|-------------|
| `Register()` | Component | Renders a registration form (username + email + password). On submit, calls the `register` API, stores the token via `loginUser()`, and navigates to `/generate`. Displays inline error messages on failure. |
| `handle(e)` | Inner Function | Updates form state from input change events. |
| `submit(e)` | Inner Function | Prevents default form submission, calls the register API, handles success/error. |

---

### `src/pages/Generate.jsx` — Image Generation Studio

| Symbol | Type | What It Does |
|--------|------|-------------|
| `StatusBadge({ status })` | Component | Renders a colour-coded pill badge for job status (`pending`, `running`, `completed`, `failed`, `cancelled`). |
| `Generate()` | Component | Main image generation page. Provides a prompt form (prompt, negative prompt, seed), submits generation requests, polls for job status updates, fetches and displays the completed image, and shows a scrollable job history sidebar with stats (attempts, best score, status). |
| `refreshJobs()` | Inner Function | Fetches all jobs via `listJobs()` and updates the jobs state (newest first). |
| `handleGenerate(e)` | Inner Function | Submits the prompt via `generateImage()`, fetches the initial job state, and sets it as the active job. Clears the prompt input on success. |
| `bestArtifact(job)` | Inner Function | **Stub** — intended to resolve the best artifact key for a job. Currently returns `null`. (See [UNIMPLEMENTED.md](UNIMPLEMENTED.md)) |
| `useEffect` (image fetch) | Effect | When the active job completes, fetches the best image as a blob URL via `fetchJobImage()` and manages cleanup of old blob URLs. |
| `useEffect` (polling) | Effect | Polls `getJob()` every 2 seconds while a job is in progress. Stops polling and refreshes the job list when the job reaches a terminal state. |
| `useEffect` (mount) | Effect | Calls `refreshJobs()` on component mount to load the job history. |
