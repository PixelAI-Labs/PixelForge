import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/useAuth';

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <nav className="fixed top-0 inset-x-0 z-50 glass">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2 group">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-purple-500 flex items-center justify-center shadow-lg shadow-brand-500/30 group-hover:shadow-brand-400/50 transition-shadow">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <path d="m21 15-5-5L5 21" />
            </svg>
          </div>
          <span className="text-lg font-bold gradient-text">PixelForge</span>
        </Link>

        {/* Right side */}
        <div className="flex items-center gap-4">
          {user ? (
            <>
              <Link
                to="/generate"
                className="text-sm font-medium text-dark-100 hover:text-white transition-colors"
              >
                Generate
              </Link>
              <span className="text-sm text-dark-200">
                {user.username}
              </span>
              <button
                onClick={() => { logout(); navigate('/'); }}
                className="btn-secondary text-sm !px-4 !py-2"
              >
                Log out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="btn-secondary text-sm !px-4 !py-2">
                Log in
              </Link>
              <Link to="/register" className="btn-primary text-sm !px-4 !py-2">
                Sign up
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
