import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { apiRequest, getStoredToken, setStoredToken } from '../api/client';
import { searchWorkspace } from '../lib/searchWorkspace';

type User = { id: number; email: string; display_name: string; is_admin: boolean };
type AuthValue = {
  token: string | null;
  user: User | null;
  setSession: (token: string, user: User) => void;
  clearSession: () => Promise<void>;
};

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(getStoredToken());
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem('rn_user');
    return raw ? (JSON.parse(raw) as User) : null;
  });
  useEffect(() => {
    const revokeChangedSession = (event: StorageEvent) => {
      if (event.key !== null && event.key !== 'rn_access_token' && event.key !== 'rn_user') return;
      // Do not adopt another tab's identity silently or retain its old request generation.
      searchWorkspace.clear();
      setToken(null);
      setUser(null);
    };
    window.addEventListener('storage', revokeChangedSession);
    return () => window.removeEventListener('storage', revokeChangedSession);
  }, []);
  const value = useMemo<AuthValue>(() => ({
    token,
    user,
    setSession: (newToken, newUser) => {
      if (user?.id !== newUser.id) searchWorkspace.clear();
      setStoredToken(newToken);
      localStorage.setItem('rn_user', JSON.stringify(newUser));
      setToken(newToken);
      setUser(newUser);
    },
    clearSession: async () => {
      searchWorkspace.clear();
      setStoredToken(null);
      localStorage.removeItem('rn_user');
      setToken(null);
      setUser(null);
      if (token) {
        try { await apiRequest('/auth/logout', { method: 'POST' }, token); } catch { /* local clear wins */ }
      }
    },
  }), [token, user]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
