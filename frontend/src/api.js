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
