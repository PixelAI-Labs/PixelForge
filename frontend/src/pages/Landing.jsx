import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/useAuth';
import desertObservatory from '../assets/landing/desert-observatory.webp';
import floatingIslands from '../assets/landing/floating-islands.webp';
import neonGreenhouse from '../assets/landing/neon-greenhouse.webp';
import oceanLibrary from '../assets/landing/ocean-library.webp';

const galleryImages = [
  {
    src: floatingIslands,
    title: 'Floating Islands',
    prompt: 'Luminous fantasy landscape',
  },
  {
    src: neonGreenhouse,
    title: 'Neon Greenhouse',
    prompt: 'Cyberpunk rooftop garden',
  },
  {
    src: oceanLibrary,
    title: 'Ocean Library',
    prompt: 'Moonlit surreal interior',
  },
  {
    src: desertObservatory,
    title: 'Desert Observatory',
    prompt: 'Cinematic sci-fi nightscape',
  },
];

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
  const [activeImage, setActiveImage] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setActiveImage((current) => (current + 1) % galleryImages.length);
    }, 4500);

    return () => window.clearInterval(timer);
  }, []);

  const showPrevious = () => {
    setActiveImage((current) => (current - 1 + galleryImages.length) % galleryImages.length);
  };

  const showNext = () => {
    setActiveImage((current) => (current + 1) % galleryImages.length);
  };

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

        {/* Generated gallery carousel */}
        <div className="mt-16 w-full max-w-5xl animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
          <div className="relative overflow-hidden rounded-2xl glass border border-dark-400/20 shadow-2xl shadow-brand-900/20">
            <div className="relative aspect-[16/9] bg-dark-800">
              {galleryImages.map((image, index) => (
                <img
                  key={image.title}
                  src={image.src}
                  alt={`${image.title} generated with PixelForge`}
                  className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-700 ${
                    index === activeImage ? 'opacity-100' : 'opacity-0'
                  }`}
                />
              ))}

              <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-dark-900/90 via-dark-900/30 to-transparent p-4 sm:p-6">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                  <div className="text-left">
                    <p className="text-xs font-semibold uppercase tracking-wide text-brand-200">
                      Generated showcase
                    </p>
                    <h2 className="mt-1 text-2xl font-bold text-white sm:text-3xl">
                      {galleryImages[activeImage].title}
                    </h2>
                    <p className="mt-1 text-sm text-dark-50">
                      {galleryImages[activeImage].prompt}
                    </p>
                  </div>

                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={showPrevious}
                      className="flex h-10 w-10 items-center justify-center rounded-full border border-white/20 bg-dark-900/60 text-white transition hover:bg-white/15 active:scale-95"
                      aria-label="Show previous generated image"
                      title="Previous image"
                    >
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="m15 18-6-6 6-6" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      onClick={showNext}
                      className="flex h-10 w-10 items-center justify-center rounded-full border border-white/20 bg-dark-900/60 text-white transition hover:bg-white/15 active:scale-95"
                      aria-label="Show next generated image"
                      title="Next image"
                    >
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="m9 18 6-6-6-6" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-center gap-2 border-t border-dark-400/20 bg-dark-800/70 px-4 py-4">
              {galleryImages.map((image, index) => (
                <button
                  key={image.title}
                  type="button"
                  onClick={() => setActiveImage(index)}
                  className={`h-2.5 rounded-full transition-all ${
                    index === activeImage ? 'w-8 bg-brand-300' : 'w-2.5 bg-dark-300 hover:bg-dark-100'
                  }`}
                  aria-label={`Show ${image.title}`}
                  title={image.title}
                />
              ))}
            </div>
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
