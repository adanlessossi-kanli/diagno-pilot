// REQ-01, REQ-7.3, REQ-7.4: Authentication context for mobile app with SecureStore persistence
import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import * as SecureStore from 'expo-secure-store';
import { createApiClient } from '@diagno-pilot/api-client';
import type { AuthUser } from '@diagno-pilot/api-client';
import { useI18n } from './I18nContext';

const API_BASE = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

// REQ 7.4: token stored under this key in SecureStore
export const TOKEN_KEY = 'diagno_access_token';

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
  // isLoading stays true until SecureStore + /auth/me resolves
  const [isLoading, setIsLoading] = useState(true);

  const { locale } = useI18n();
  const localeRef = useRef(locale);
  useEffect(() => { localeRef.current = locale; }, [locale]);

  // REQ-7.3: inject Accept-Language on every API call via getLocale getter
  const apiClient = createApiClient(API_BASE, () => token, () => localeRef.current);

  // REQ 7.4: On startup, read token from SecureStore and restore session
  useEffect(() => {
    (async () => {
      try {
        const stored = await SecureStore.getItemAsync(TOKEN_KEY);
        if (stored) {
          // Validate the stored token by calling /auth/me
          const me = await createApiClient(API_BASE, () => stored).auth.me();
          setToken(stored);
          setUser(me);
        }
      } catch {
        // Token invalid or /auth/me returned 401 — clear stored token
        await SecureStore.deleteItemAsync(TOKEN_KEY);
        setToken(null);
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiClient.auth.login(email, password);
    // Auth is now cookie-based; access_token is set as an httpOnly cookie by the server.
    // We store the user info from the response and fetch the full profile via /auth/me.
    const me = await apiClient.auth.me();
    // Store a placeholder token value so the rest of the app knows we're authenticated.
    const placeholder = `session:${res.expires_in}`;
    await SecureStore.setItemAsync(TOKEN_KEY, placeholder);
    setToken(placeholder);
    setUser(me);
  }, [apiClient]);

  const logout = useCallback(async () => {
    try { await apiClient.auth.logout(); } catch { /* ignore backend errors */ }
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
