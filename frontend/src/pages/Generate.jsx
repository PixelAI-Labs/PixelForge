import { useEffect, useRef, useState } from 'react';
import { generateImage, getJob, listJobs, fetchJobImage } from '../api';

const POLL_MS = 2000;

function StatusBadge({ status }) {
  const map = {
    pending: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    running: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    completed: 'bg-green-500/20 text-green-400 border-green-500/30',
    failed: 'bg-red-500/20 text-red-400 border-red-500/30',
    cancelled: 'bg-dark-300/20 text-dark-100 border-dark-400/30',
  };
  return (
    <span className={`inline-block text-xs font-semibold px-2.5 py-1 rounded-full border ${map[status] || map.pending}`}>
      {status}
    </span>
  );
}

export default function Generate() {
  const [prompt, setPrompt] = useState('');
  const [negativePrompt, setNegativePrompt] = useState('');
  const [seed, setSeed] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [jobs, setJobs] = useState([]);
  const [activeJob, setActiveJob] = useState(null);
  const [error, setError] = useState('');
  const pollRef = useRef(null);
  const [imageUrl, setImageUrl] = useState(null);
  const [imageError, setImageError] = useState('');
  const [imageLoading, setImageLoading] = useState(false);

  // Fetch image when active job is completed
  useEffect(() => {
    if (!activeJob) { setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; }); setImageError(''); return; }
    const status = activeJob.status || activeJob.state;
    if (status !== 'completed') { setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; }); setImageError(''); return; }

    let cancelled = false;
    setImageLoading(true);
    setImageError('');

    fetchJobImage(activeJob.job_id)
      .then((url) => {
        if (!cancelled) {
          setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return url; });
          setImageLoading(false);
        } else {
          URL.revokeObjectURL(url);
        }
      })
      .catch((err) => {
        if (!cancelled) { setImageError(err.message); setImageLoading(false); }
      });

    return () => { cancelled = true; };
  }, [activeJob?.job_id, activeJob?.status, activeJob?.state]);

  // Poll active job
  useEffect(() => {
    if (!activeJob || ['completed', 'failed', 'cancelled'].includes(activeJob.status)) {
      clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const j = await getJob(activeJob.job_id);
        setActiveJob(j);
        if (['completed', 'failed', 'cancelled'].includes(j.status)) {
          clearInterval(pollRef.current);
          refreshJobs();
        }
      } catch { /* ignore */ }
    }, POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [activeJob?.job_id, activeJob?.status]);

  async function refreshJobs() {
    try {
      const list = await listJobs();
      setJobs(list.reverse());
    } catch { /* ignore */ }
  }

  useEffect(() => { refreshJobs(); }, []);

  async function handleGenerate(e) {
    e.preventDefault();
    if (!prompt.trim()) return;
    setError('');
    setSubmitting(true);
    try {
      const { job_id } = await generateImage(
        prompt.trim(),
        seed ? parseInt(seed, 10) : null,
        negativePrompt.trim(),
      );
      const j = await getJob(job_id);
      setActiveJob(j);
      setPrompt('');
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  // Find best artifact from jobs list for display
  function bestArtifact(job) {
    // job object from listJobs has best_attempt; we need the artifact key
    // In a full implementation you'd look this up; for now show via /artifacts endpoint
    return null;
  }

  return (
    <div className="min-h-screen pt-24 pb-12 px-4 sm:px-6">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">
          <span className="gradient-text">Image Studio</span>
        </h1>
        <p className="text-dark-100 mb-10">Describe what you want to create and let PixelForge handle the rest.</p>

        <div className="grid lg:grid-cols-5 gap-8">
          {/* Left: Form */}
          <div className="lg:col-span-2 space-y-6">
            <form onSubmit={handleGenerate} className="space-y-5">
              {/* Prompt */}
              <div>
                <label className="block text-sm font-medium text-dark-100 mb-1.5">Prompt</label>
                <textarea
                  rows={4}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="A majestic castle floating above the clouds, fantasy digital art, highly detailed…"
                  className="input-field resize-none"
                  required
                />
              </div>

              {/* Negative prompt */}
              <div>
                <label className="block text-sm font-medium text-dark-100 mb-1.5">
                  Negative Prompt <span className="text-dark-300">(optional)</span>
                </label>
                <input
                  type="text"
                  value={negativePrompt}
                  onChange={(e) => setNegativePrompt(e.target.value)}
                  placeholder="blurry, low quality, deformed"
                  className="input-field"
                />
              </div>

              {/* Seed */}
              <div>
                <label className="block text-sm font-medium text-dark-100 mb-1.5">
                  Seed <span className="text-dark-300">(optional)</span>
                </label>
                <input
                  type="number"
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                  placeholder="Random"
                  className="input-field"
                />
              </div>

              {error && (
                <div className="px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={submitting || !prompt.trim()}
                className="btn-primary w-full flex items-center justify-center gap-2"
              >
                {submitting ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-white" />
                    Submitting…
                  </>
                ) : (
                  <>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                    Generate
                  </>
                )}
              </button>
            </form>

            {/* History */}
            {jobs.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-dark-200 uppercase tracking-wide mb-3">History</h3>
                <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                  {jobs.map((j) => (
                    <button
                      key={j.job_id}
                      onClick={() => setActiveJob(j)}
                      className={`w-full text-left px-4 py-3 rounded-xl border transition-colors text-sm ${
                        activeJob?.job_id === j.job_id
                          ? 'border-brand-500/50 bg-brand-600/10'
                          : 'border-dark-400/30 bg-dark-700/40 hover:bg-dark-600/50'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium truncate mr-2">{j.prompt?.slice(0, 40) || j.job_id.slice(0, 12)}</span>
                        <StatusBadge status={j.state || j.status} />
                      </div>
                      <div className="text-xs text-dark-300">
                        Score: {j.best_score ?? '—'} &middot; Attempts: {j.attempts ?? 0}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right: Display */}
          <div className="lg:col-span-3">
            {activeJob ? (
              <div className="glass rounded-2xl p-6 space-y-4 animate-fade-in-up">
                <div className="flex items-center justify-between">
                  <h2 className="font-semibold text-lg truncate pr-4">
                    {activeJob.prompt?.slice(0, 60) || 'Generation'}
                  </h2>
                  <StatusBadge status={activeJob.state || activeJob.status} />
                </div>

                {/* Image area */}
                <div className="aspect-square rounded-xl bg-dark-800 border border-dark-400/20 flex items-center justify-center overflow-hidden">
                  {(activeJob.status || activeJob.state) === 'completed' ? (
                    imageLoading ? (
                      <div className="flex flex-col items-center gap-3 text-dark-200">
                        <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-brand-500" />
                        <p className="text-sm">Loading image…</p>
                      </div>
                    ) : imageError ? (
                      <div className="text-center text-red-400 px-4">
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="mx-auto mb-2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                        <p className="text-sm font-medium mb-1">Image unavailable</p>
                        <p className="text-xs text-red-400/70">{imageError}</p>
                      </div>
                    ) : imageUrl ? (
                      <img
                        src={imageUrl}
                        alt="Generated"
                        className="w-full h-full object-contain"
                      />
                    ) : null
                  ) : (activeJob.status || activeJob.state) === 'failed' ? (
                    <div className="text-center text-red-400">
                      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="mx-auto mb-2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                      <p className="text-sm">{activeJob.error || 'Generation failed'}</p>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-3 text-dark-200">
                      <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-brand-500" />
                      <p className="text-sm">Generating image…</p>
                      <p className="text-xs text-dark-300">This may take a minute on first run</p>
                    </div>
                  )}
                </div>

                {/* Stats */}
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div className="glass rounded-xl py-3">
                    <div className="text-2xl font-bold">{activeJob.attempts ?? 0}</div>
                    <div className="text-xs text-dark-200">Attempts</div>
                  </div>
                  <div className="glass rounded-xl py-3">
                    <div className="text-2xl font-bold">{activeJob.best_score ?? '—'}</div>
                    <div className="text-xs text-dark-200">Best Score</div>
                  </div>
                  <div className="glass rounded-xl py-3">
                    <div className="text-2xl font-bold capitalize">{activeJob.state || activeJob.status}</div>
                    <div className="text-xs text-dark-200">Status</div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="glass rounded-2xl h-full min-h-[400px] flex flex-col items-center justify-center text-dark-200">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="mb-4 opacity-40">
                  <rect x="3" y="3" width="18" height="18" rx="2"/>
                  <circle cx="8.5" cy="8.5" r="1.5"/>
                  <path d="m21 15-5-5L5 21"/>
                </svg>
                <p className="text-lg font-medium mb-1">No image yet</p>
                <p className="text-sm text-dark-300">Enter a prompt and hit Generate to get started</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
