/**
 * API client for PixelForge backend.
 *
 * In dev mode Vite proxies /api → http://localhost:8000.
 * In production the backend URL is set via VITE_API_URL env var.
 */

const BASE = import.meta.env.VITE_API_URL || '/api';

function authHeaders() {
  const token = localStorage.getItem('pf_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...options.headers,
    },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const error = new Error(body.detail || `Request failed (${res.status})`);
    error.status = res.status;
    throw error;
  }
  // 204 or empty body
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

// ---- Auth -------------------------------------------------------

export async function register(username, email, password) {
  return request('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, email, password }),
  });
}

export async function login(email, password) {
  return request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export async function getMe() {
  return request('/auth/me');
}

// ---- Generation -------------------------------------------------

export async function generateImage(prompt, seed = null, negativePrompt = '') {
  return request('/generate', {
    method: 'POST',
    body: JSON.stringify({
      prompt,
      seed,
      negative_prompt: negativePrompt,
    }),
  });
}

export async function getJob(jobId) {
  return request(`/jobs/${jobId}`);
}

export async function listJobs() {
  return request('/jobs');
}

export function artifactUrl(artifactId) {
  return `${BASE}/artifacts/${artifactId}`;
}

export function jobImageUrl(jobId) {
  return `${BASE}/jobs/${jobId}/image`;
}

/**
 * Fetch the best image for a job as a Blob URL.
 * Uses auth headers and provides proper error reporting.
 * Returns { url: string } on success, throws on failure.
 */
export async function fetchJobImage(jobId) {
  const res = await fetch(`${BASE}/jobs/${jobId}/image`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Image fetch failed (${res.status})`);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

// ---- Iterative Editing ------------------------------------------

export async function createEditSession(prompt, seed = null, negativePrompt = '') {
  return request('/generate-session', {
    method: 'POST',
    body: JSON.stringify({
      prompt,
      seed,
      negative_prompt: negativePrompt,
    }),
  });
}

export async function editImage(sessionId, editInstruction, strength = 0.35) {
  return request('/edit', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      edit_instruction: editInstruction,
      strength,
    }),
  });
}

export async function listSessions() {
  return request('/sessions');
}

export async function getSession(sessionId) {
  return request(`/sessions/${sessionId}`);
}

export async function endSession(sessionId) {
  return request(`/sessions/${sessionId}`, { method: 'DELETE' });
}

export async function fetchSessionImage(sessionId, iteration) {
  const res = await fetch(`${BASE}/sessions/${sessionId}/image/${iteration}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Image fetch failed (${res.status})`);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}
