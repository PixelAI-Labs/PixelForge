import { createContext, useEffect, useState } from 'react';
import { getMe } from '../api';

const AuthContext = createContext(null);

export { AuthContext };

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // On mount, validate the stored token
  useEffect(() => {
    const token = localStorage.getItem('pf_token');
    if (!token) {
      setLoading(false);
      return;
    }
    getMe()
      .then((u) => setUser(u))
      .catch(() => {
        localStorage.removeItem('pf_token');
      })
      .finally(() => setLoading(false));
  }, []);

  function loginUser(data) {
    localStorage.setItem('pf_token', data.access_token);
    setUser({ user_id: data.user_id, username: data.username });
  }

  function logout() {
    localStorage.removeItem('pf_token');
    setUser(null);
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-dark-900">
        <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-brand-500" />
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ user, loginUser, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
