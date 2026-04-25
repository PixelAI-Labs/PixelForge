import { useEffect, useRef, useState } from 'react';
import {
  generateImage, getJob, listJobs, fetchJobImage,
  createEditSession, editImage, getSession, listSessions, fetchSessionImage, endSession,
} from '../api';

const POLL_MS = 2000;
const EDIT_STRENGTH = 1.0;

function CreationLoadingOverlay({ message }) {
  return (
    <div className="fixed inset-0 z-50 bg-dark-900/85 backdrop-blur-sm flex items-center justify-center px-6">
      <div className="glass rounded-2xl p-8 w-full max-w-md text-center border-brand-500/30 shadow-2xl shadow-brand-900/30">
        <div className="mx-auto mb-5 h-14 w-14 rounded-full border-4 border-brand-500/20 border-t-brand-400 animate-spin" />
        <h3 className="text-xl font-semibold mb-2">
          <span className="gradient-text">Working On Your Image</span>
        </h3>
        <p className="text-dark-100 text-sm">{message}</p>
      </div>
    </div>
  );
}

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
  const [sessions, setSessions] = useState([]);
  const [activeJob, setActiveJob] = useState(null);
  const [error, setError] = useState('');
  const pollRef = useRef(null);
  const [imageUrl, setImageUrl] = useState(null);
  const [imageError, setImageError] = useState('');
  const [imageLoading, setImageLoading] = useState(false);

  // Job thumbnail cache: { job_id: blobUrl }
  const [jobThumbs, setJobThumbs] = useState({});
  const fetchedThumbsRef = useRef(new Set());

  // Iterative editing state
  const [sessionId, setSessionId] = useState(null);
  const [session, setSession] = useState(null);
  const [editInstruction, setEditInstruction] = useState('');
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState('');
  const [iterationImages, setIterationImages] = useState({});  // { iteration: blobUrl }
  const [selectedIteration, setSelectedIteration] = useState(null);
  const sessionPollRef = useRef(null);
  const fetchedItersRef = useRef(new Set());
  const prevIterCountRef = useRef(0);
  const [isEditProcessing, setIsEditProcessing] = useState(false);
  const pendingEditIterationRef = useRef(null);
  const editProcessingTimeoutRef = useRef(null);

  function clearEditProcessingState() {
    pendingEditIterationRef.current = null;
    if (editProcessingTimeoutRef.current) {
      clearTimeout(editProcessingTimeoutRef.current);
      editProcessingTimeoutRef.current = null;
    }
    setIsEditProcessing(false);
  }

  const isJobGenerating = Boolean(activeJob && ['pending', 'running'].includes(activeJob.state));
  const isSessionInitializing = Boolean(sessionId && (!session || session.iterations.length === 0));
  const showCreationLoader = submitting || isJobGenerating || isSessionInitializing || isEditProcessing;

  const creationMessage = isEditProcessing
    ? 'Applying your edit and rendering the next iteration...'
    : isSessionInitializing
      ? 'Creating the initial session image...'
      : isJobGenerating
        ? 'Generating your image. This may take up to a minute...'
        : 'Submitting your generation request...';

  // Fetch image when active job is completed
  useEffect(() => {
    if (!activeJob) { setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; }); setImageError(''); return; }
    if (activeJob.state !== 'completed') { setImageUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; }); setImageError(''); return; }

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
  }, [activeJob?.job_id, activeJob?.state]);

  // Poll active job
  useEffect(() => {
    if (!activeJob || ['completed', 'failed', 'cancelled'].includes(activeJob.state)) {
      clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const j = await getJob(activeJob.job_id);
        setActiveJob(j);
        if (['completed', 'failed', 'cancelled'].includes(j.state)) {
          clearInterval(pollRef.current);
          refreshJobs();
        }
      } catch { /* ignore */ }
    }, POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [activeJob?.job_id, activeJob?.state]);

  async function refreshJobs() {
    try {
      const list = await listJobs();
      setJobs(list.reverse());
    } catch { /* ignore */ }
  }

  async function refreshSessions() {
    try {
      const list = await listSessions();
      setSessions(list);
    } catch { /* ignore */ }
  }

  useEffect(() => { refreshJobs(); refreshSessions(); }, []);

  // Fetch thumbnails for completed jobs in history
  useEffect(() => {
    for (const j of jobs) {
      if (j.state === 'completed' && !fetchedThumbsRef.current.has(j.job_id)) {
        fetchedThumbsRef.current.add(j.job_id);
        fetchJobImage(j.job_id)
          .then((url) => {
            setJobThumbs((prev) => ({ ...prev, [j.job_id]: url }));
          })
          .catch(() => {
            fetchedThumbsRef.current.delete(j.job_id);
          });
      }
    }
  }, [jobs]);

  // Poll edit session for new iterations
  useEffect(() => {
    if (!sessionId) {
      fetchedItersRef.current = new Set();
      clearEditProcessingState();
      return;
    }
    const poll = async () => {
      try {
        const s = await getSession(sessionId);
        setSession(s);
        // Auto-select latest iteration when new ones appear
        if (s.iterations.length > prevIterCountRef.current) {
          prevIterCountRef.current = s.iterations.length;
          const latest = s.iterations[s.iterations.length - 1];
          if (latest.artifact_id) {
            setSelectedIteration(latest.iteration);
          }
        }
        // Load images for new iterations (use ref to avoid stale closure re-fetches)
        for (const it of s.iterations) {
          if (it.artifact_id && !fetchedItersRef.current.has(it.iteration)) {
            fetchedItersRef.current.add(it.iteration);
            fetchSessionImage(sessionId, it.iteration)
              .then((url) => {
                setIterationImages((prev) => {
                  if (prev[it.iteration]) URL.revokeObjectURL(prev[it.iteration]);
                  return { ...prev, [it.iteration]: url };
                });
                if (pendingEditIterationRef.current === it.iteration) {
                  clearEditProcessingState();
                }
              })
              .catch(() => {
                fetchedItersRef.current.delete(it.iteration);
                if (pendingEditIterationRef.current === it.iteration) {
                  clearEditProcessingState();
                }
              });
          }
        }
      } catch { /* ignore */ }
    };
    poll();
    sessionPollRef.current = setInterval(poll, POLL_MS);
    return () => clearInterval(sessionPollRef.current);
  }, [sessionId]);

  // Cleanup iteration blob URLs on unmount
  useEffect(() => {
    return () => {
      Object.values(iterationImages).forEach((url) => URL.revokeObjectURL(url));
      if (editProcessingTimeoutRef.current) {
        clearTimeout(editProcessingTimeoutRef.current);
      }
    };
  }, []);

  async function handleEdit(e) {
    e.preventDefault();
    if (!editInstruction.trim() || !sessionId) return;
    setEditError('');
    setEditSubmitting(true);
    const nextIteration = session?.iterations?.length ?? 0;
    clearEditProcessingState();
    pendingEditIterationRef.current = nextIteration;
    setIsEditProcessing(true);
    editProcessingTimeoutRef.current = setTimeout(() => {
      if (pendingEditIterationRef.current === nextIteration) {
        clearEditProcessingState();
        setEditError('Edit is taking longer than expected. Please try again.');
      }
    }, 90000);
    try {
      await editImage(sessionId, editInstruction.trim(), EDIT_STRENGTH);
      setEditInstruction('');
      // Session poll will pick up the new iteration
    } catch (err) {
      setEditError(err.message);
      clearEditProcessingState();
    } finally {
      setEditSubmitting(false);
    }
  }

  async function handleEndSession() {
    if (!sessionId) return;
    try {
      await endSession(sessionId);
    } catch { /* ignore — session may already be gone */ }
    clearSessionView();
    setEditInstruction('');
    setEditError('');
    refreshSessions();
    refreshJobs();  // session promoted to gallery on end
  }

  function clearSessionView() {
    clearInterval(sessionPollRef.current);
    fetchedItersRef.current = new Set();
    prevIterCountRef.current = 0;
    clearEditProcessingState();
    setSessionId(null);
    setSession(null);
    setSelectedIteration(null);
    Object.values(iterationImages).forEach((url) => URL.revokeObjectURL(url));
    setIterationImages({});
  }

  async function handleResumeSession(sid) {
    // Clear any existing session/job state before resuming a session
    clearSessionView();
    setActiveJob(null);
    // Load the session
    setSessionId(sid);
  }

  async function handleGenerateSession(e) {
    e.preventDefault();
    if (!prompt.trim()) return;
    setError('');
    setSubmitting(true);
    setActiveJob(null);
    setSession(null);
    setIterationImages({});
    setSelectedIteration(null);
    fetchedItersRef.current = new Set();
    prevIterCountRef.current = 0;
    clearEditProcessingState();
    try {
      const { session_id } = await createEditSession(
        prompt.trim(),
        seed ? parseInt(seed, 10) : null,
        negativePrompt.trim(),
      );
      setSessionId(session_id);
      refreshSessions();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGenerate(e) {
    e.preventDefault();
    if (!prompt.trim()) return;
    setError('');
    setSubmitting(true);
    clearSessionView();
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
    <>
      {showCreationLoader && (
        <CreationLoadingOverlay message={creationMessage} />
      )}
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

              <button
                type="button"
                disabled={submitting || !prompt.trim()}
                onClick={handleGenerateSession}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-brand-500/50 text-brand-400 hover:bg-brand-600/10 transition-colors text-sm font-medium"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
                Generate &amp; Edit Session
              </button>
            </form>

            {/* History */}
            {(jobs.length > 0 || sessions.length > 0) && (
              <div>
                <h3 className="text-sm font-semibold text-dark-200 uppercase tracking-wide mb-3">History</h3>
                <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                  {/* Edit Sessions */}
                  {sessions.map((s) => (
                    <button
                      key={s.session_id}
                      onClick={() => handleResumeSession(s.session_id)}
                      className={`w-full text-left px-3 py-2.5 rounded-xl border transition-colors text-sm ${
                        sessionId === s.session_id
                          ? 'border-purple-500/50 bg-purple-600/10'
                          : 'border-dark-400/30 bg-dark-700/40 hover:bg-dark-600/50'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className="flex-shrink-0 w-14 h-14 rounded-lg overflow-hidden bg-dark-800 border border-purple-400/30 flex items-center justify-center text-purple-400">
                          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-medium truncate mr-2">{s.original_prompt?.slice(0, 30) || s.session_id.slice(0, 12)}</span>
                            <span className="inline-block text-xs font-semibold px-2.5 py-1 rounded-full border bg-purple-500/20 text-purple-400 border-purple-500/30">session</span>
                          </div>
                          <div className="text-xs text-dark-300">
                            {s.iteration_count} iteration{s.iteration_count !== 1 ? 's' : ''}
                          </div>
                        </div>
                      </div>
                    </button>
                  ))}
                  {/* Jobs */}
                  {jobs.map((j) => (
                    <button
                      key={j.job_id}
                      onClick={() => {
                        clearSessionView();
                        setActiveJob(j);
                      }}
                      className={`w-full text-left px-3 py-2.5 rounded-xl border transition-colors text-sm ${
                        activeJob?.job_id === j.job_id
                          ? 'border-brand-500/50 bg-brand-600/10'
                          : 'border-dark-400/30 bg-dark-700/40 hover:bg-dark-600/50'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        {/* Thumbnail */}
                        <div className="flex-shrink-0 w-14 h-14 rounded-lg overflow-hidden bg-dark-800 border border-dark-400/20">
                          {jobThumbs[j.job_id] ? (
                            <img src={jobThumbs[j.job_id]} alt="" className="w-full h-full object-cover" />
                          ) : j.state === 'completed' ? (
                            <div className="w-full h-full flex items-center justify-center">
                              <div className="animate-spin rounded-full h-3 w-3 border-t-2 border-brand-500" />
                            </div>
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-dark-300">
                              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>
                            </div>
                          )}
                        </div>
                        {/* Info */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-medium truncate mr-2">{j.prompt?.slice(0, 30) || j.job_id.slice(0, 12)}</span>
                            <StatusBadge status={j.state} />
                          </div>
                          <div className="text-xs text-dark-300">
                            Score: {j.best_score ?? '—'} &middot; Attempts: {j.attempts ?? 0}
                          </div>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right: Display */}
          <div className="lg:col-span-3 space-y-6">
            {/* Edit Session Panel */}
            {sessionId && session && session.iterations.length > 0 && (
              <div className="glass rounded-2xl p-6 space-y-4 animate-fade-in-up">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold text-lg">
                  <span className="gradient-text">Edit Session</span>
                </h2>
                <button
                  onClick={handleEndSession}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-500/40 text-red-400 hover:bg-red-500/10 transition-colors text-xs font-medium"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  End Session
                </button>
              </div>

                {/* Iteration Timeline */}
                <div className="flex gap-2 overflow-x-auto pb-2">
                  {session.iterations.map((it) => (
                    <button
                      key={it.iteration}
                      onClick={() => setSelectedIteration(it.iteration)}
                      className={`flex-shrink-0 w-20 rounded-lg border-2 overflow-hidden transition-all ${
                        selectedIteration === it.iteration
                          ? 'border-brand-500 ring-2 ring-brand-500/30'
                          : 'border-dark-400/30 hover:border-dark-300'
                      }`}
                    >
                      {iterationImages[it.iteration] ? (
                        <img src={iterationImages[it.iteration]} alt={`Iteration ${it.iteration}`} className="w-full h-20 object-cover" />
                      ) : (
                        <div className="w-full h-20 flex items-center justify-center bg-dark-800">
                          <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-brand-500" />
                        </div>
                      )}
                      <div className="text-[10px] text-center py-0.5 text-dark-200 truncate px-1">
                        {it.iteration === 0 ? 'Original' : it.edit_instruction?.slice(0, 12) || `Edit ${it.iteration}`}
                      </div>
                    </button>
                  ))}
                </div>

                {/* Selected iteration image */}
                <div className="relative aspect-square rounded-xl bg-dark-800 border border-dark-400/20 flex items-center justify-center overflow-hidden group">
                  {selectedIteration !== null && iterationImages[selectedIteration] ? (
                    <img
                      src={iterationImages[selectedIteration]}
                      alt={`Iteration ${selectedIteration}`}
                      className="w-full h-full object-contain"
                    />
                  ) : iterationImages[0] ? (
                    <img
                      src={iterationImages[0]}
                      alt="Original"
                      className="w-full h-full object-contain"
                    />
                  ) : (
                    <div className="flex flex-col items-center gap-3 text-dark-200">
                      <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-brand-500" />
                      <p className="text-sm">{selectedIteration !== null && selectedIteration > 0 ? 'Applying edit…' : 'Generating initial image…'}</p>
                    </div>
                  )}
                  {(selectedIteration !== null ? iterationImages[selectedIteration] : iterationImages[0]) && (
                    <a
                      href={selectedIteration !== null ? iterationImages[selectedIteration] : iterationImages[0]}
                      download={`pixelforge-session-${sessionId}-iter${selectedIteration ?? 0}.png`}
                      className="absolute top-3 right-3 p-2 rounded-lg bg-dark-900/70 border border-dark-400/30 text-dark-100 hover:text-white hover:bg-dark-900/90 transition-all opacity-0 group-hover:opacity-100"
                      title="Download image"
                    >
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    </a>
                  )}
                </div>

                {/* Edit form */}
                <form onSubmit={handleEdit} className="flex gap-2">
                  <input
                    type="text"
                    value={editInstruction}
                    onChange={(e) => setEditInstruction(e.target.value)}
                    placeholder="e.g. add neon lights, make it nighttime…"
                    className="input-field flex-1"
                  />
                  <button
                    type="submit"
                    disabled={editSubmitting || !editInstruction.trim()}
                    className="btn-primary px-4 flex items-center gap-1.5 whitespace-nowrap"
                  >
                    {editSubmitting ? (
                      <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-white" />
                    ) : (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
                    )}
                    Edit
                  </button>
                </form>

                {editError && (
                  <div className="px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
                    {editError}
                  </div>
                )}

                {/* Iteration info */}
                <div className="grid grid-cols-2 gap-4 text-center">
                  <div className="glass rounded-xl py-3">
                    <div className="text-2xl font-bold">{session.iterations.length}</div>
                    <div className="text-xs text-dark-200">Iterations</div>
                  </div>
                  <div className="glass rounded-xl py-3">
                    <div className="text-2xl font-bold text-sm truncate px-2">{session.original_prompt?.slice(0, 20) || '—'}</div>
                    <div className="text-xs text-dark-200">Base Prompt</div>
                  </div>
                </div>
              </div>
            )}

            {!sessionId && (activeJob ? (
              <div className="glass rounded-2xl p-6 space-y-4 animate-fade-in-up">
                <div className="flex items-center justify-between">
                  <h2 className="font-semibold text-lg truncate pr-4">
                    {activeJob.prompt?.slice(0, 60) || 'Generation'}
                  </h2>
                  <StatusBadge status={activeJob.state} />
                </div>

                {/* Image area */}
                <div className="relative aspect-square rounded-xl bg-dark-800 border border-dark-400/20 flex items-center justify-center overflow-hidden group">
                  {activeJob.state === 'completed' ? (
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
                      <>
                        <img
                          src={imageUrl}
                          alt="Generated"
                          className="w-full h-full object-contain"
                        />
                        <a
                          href={imageUrl}
                          download={`pixelforge-${activeJob.job_id}.png`}
                          className="absolute top-3 right-3 p-2 rounded-lg bg-dark-900/70 border border-dark-400/30 text-dark-100 hover:text-white hover:bg-dark-900/90 transition-all opacity-0 group-hover:opacity-100"
                          title="Download image"
                        >
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                        </a>
                      </>
                    ) : null
                  ) : activeJob.state === 'failed' ? (
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
                    <div className="text-2xl font-bold capitalize">{activeJob.state}</div>
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
            ))}
          </div>
        </div>
      </div>
      </div>
    </>
  );
}
