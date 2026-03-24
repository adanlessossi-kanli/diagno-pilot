// REQ-01: Authentication context for mobile app
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import * as SecureStore from 'expo-secure-store';
import { createApiClient } from '@diagno-pilot/api-client';
import type { AuthUser } from '@diagno-pilot/api-client';

const API_BASE = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';
const TOKEN_KEY = 'diagno_pilot_token';

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  apiClient: ReturnType<typeof createApiClient>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const apiClient = createApiClient(API_BASE, () => token);

  useEffect(() => {
    SecureStore.getItemAsync(TOKEN_KEY).then(async (stored) => {
      if (stored) {
        setToken(stored);
        try {
          const me = await createApiClient(API_BASE, () => stored).auth.me();
          setUser(me);
        } catch {
          await SecureStore.deleteItemAsync(TOKEN_KEY);
        }
      }
      setIsLoading(false);
    });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiClient.auth.login(email, password);
    await SecureStore.setItemAsync(TOKEN_KEY, res.access_token);
    setToken(res.access_token);
    setUser(res.user);
  }, [apiClient]);

  const logout = useCallback(async () => {
    try { await apiClient.auth.logout(); } catch { /* ignore */ }
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, [apiClient]);

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout, apiClient }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
