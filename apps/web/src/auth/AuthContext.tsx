import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { apiRequest, getStoredToken, setStoredToken } from '../api/client';

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
  const value = useMemo<AuthValue>(() => ({
    token,
    user,
    setSession: (newToken, newUser) => {
      setStoredToken(newToken);
      localStorage.setItem('rn_user', JSON.stringify(newUser));
      setToken(newToken);
      setUser(newUser);
    },
    clearSession: async () => {
      if (token) {
        try { await apiRequest('/auth/logout', { method: 'POST' }, token); } catch { /* local clear wins */ }
      }
      setStoredToken(null);
      localStorage.removeItem('rn_user');
      setToken(null);
      setUser(null);
    },
  }), [token, user]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
