import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const features = [
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5Z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
    ),
    title: 'Adaptive Sampling',
    desc: 'Automatically adjusts diffusion parameters to maximise quality score in fewer attempts.',
  },
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 113 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
    ),
    title: 'Quality Evaluation',
    desc: 'Built-in CLIP-based evaluator scores every attempt so only the best image is returned.',
  },
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
    ),
    title: 'GPU Orchestration',
    desc: 'FIFO job queue with GPU mutex ensures safe, sequential access to VRAM.',
  },
];

export default function Landing() {
  const { user } = useAuth();

  return (
    <div className="relative overflow-hidden">
      {/* Background blobs */}
      <div className="absolute -top-40 -left-40 w-[500px] h-[500px] rounded-full bg-brand-600/20 blur-[120px] animate-pulse-glow" />
      <div className="absolute top-1/3 -right-40 w-[400px] h-[400px] rounded-full bg-purple-600/20 blur-[120px] animate-pulse-glow" style={{ animationDelay: '1.5s' }} />

      {/* Hero */}
      <section className="relative pt-36 pb-28 px-6 flex flex-col items-center text-center max-w-4xl mx-auto">
        <div className="animate-fade-in-up">
          <span className="inline-block px-4 py-1.5 rounded-full text-xs font-semibold tracking-wide uppercase bg-brand-600/20 text-brand-300 border border-brand-500/30 mb-6">
            Stable Diffusion 1.5 &middot; Self-hosted
          </span>
          <h1 className="text-5xl sm:text-6xl md:text-7xl font-extrabold leading-tight tracking-tight">
            Forge stunning images<br />
            <span className="gradient-text">with AI precision</span>
          </h1>
          <p className="mt-6 text-lg sm:text-xl text-dark-100 max-w-2xl mx-auto">
            PixelForge runs Stable Diffusion on your own GPU, adaptive-tunes every parameter, and picks the highest-quality result — all through a simple, elegant interface.
          </p>

          <div className="flex flex-wrap gap-4 justify-center mt-10">
            {user ? (
              <Link to="/generate" className="btn-primary text-lg !px-8 !py-4">
                Open Studio
              </Link>
            ) : (
              <>
                <Link to="/register" className="btn-primary text-lg !px-8 !py-4">
                  Get Started — Free
                </Link>
                <Link to="/login" className="btn-secondary text-lg !px-8 !py-4">
                  Log in
                </Link>
              </>
            )}
          </div>
        </div>

        {/* Hero image placeholder */}
        <div className="mt-16 w-full max-w-3xl aspect-video rounded-2xl glass border border-dark-400/20 flex items-center justify-center animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
          <div className="flex flex-col items-center gap-3 text-dark-200">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <path d="m21 15-5-5L5 21" />
            </svg>
            <span className="text-sm">Your generated masterpiece appears here</span>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="relative py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl sm:text-4xl font-bold text-center mb-16">
            Why <span className="gradient-text">PixelForge</span>?
          </h2>
          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((f, i) => (
              <div
                key={i}
                className="glass rounded-2xl p-8 hover:border-brand-500/40 transition-colors group"
              >
                <div className="w-14 h-14 rounded-xl bg-brand-600/20 flex items-center justify-center text-brand-400 mb-5 group-hover:bg-brand-600/30 transition-colors">
                  {f.icon}
                </div>
                <h3 className="text-xl font-semibold mb-2">{f.title}</h3>
                <p className="text-dark-100 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="relative py-24 px-6 text-center">
        <div className="max-w-2xl mx-auto">
          <h2 className="text-3xl sm:text-4xl font-bold mb-4">
            Ready to create?
          </h2>
          <p className="text-dark-100 text-lg mb-8">
            Sign up in seconds and start generating — no API keys, no rate limits.
          </p>
          {user ? (
            <Link to="/generate" className="btn-primary text-lg !px-8 !py-4">
              Open Studio
            </Link>
          ) : (
            <Link to="/register" className="btn-primary text-lg !px-8 !py-4">
              Create your free account
            </Link>
          )}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-dark-400/20 py-8 text-center text-sm text-dark-200">
        &copy; {new Date().getFullYear()} PixelForge &mdash; Self-hosted AI image generation.
      </footer>
    </div>
  );
}
