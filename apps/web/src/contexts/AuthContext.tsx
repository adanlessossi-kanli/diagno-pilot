'use client';

import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { createApiClient } from '@diagno-pilot/api-client';
import type { AuthUser, UserRole } from '@diagno-pilot/types';

// Re-export so existing imports of AuthUser from this module continue to work
export type { AuthUser } from '@diagno-pilot/types';

// ─── Types ────────────────────────────────────────────────────────────────────

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  fetchWithRefresh: (input: RequestInfo, init?: RequestInit) => Promise<Response>;
  getToken: () => string | null;
}

// ─── Context ──────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

// ─── Provider ─────────────────────────────────────────────────────────────────

export function AuthProvider({ children, locale }: { children: React.ReactNode; locale: string }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  // isLoading stays true until /auth/me resolves (REQ 7.2)
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();
  // Prevent concurrent refresh attempts
  const isRefreshing = useRef(false);
  // In-memory token — scoped to this provider instance (no module-level mutable)
  const memoryTokenRef = useRef<string | null>(null);

  const getToken = useCallback((): string | null => {
    return memoryTokenRef.current;
  }, []); // stable — memoryTokenRef never changes

  const apiClient = React.useMemo(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
    return createApiClient(baseUrl, getToken);
  }, [getToken]);

  /**
   * Attempt a silent token refresh.
   * Returns true if a new access token was obtained, false otherwise.
   */
  const tryRefresh = useCallback(async (): Promise<boolean> => {
    if (isRefreshing.current) return false;
    isRefreshing.current = true;
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
      const res = await fetch(`${baseUrl}/api/v1/auth/refresh`, {
        method: 'POST',
        credentials: 'include', // send httpOnly refresh token cookie
      });
      if (!res.ok) return false;
      const data = (await res.json()) as { access_token: string };
      memoryTokenRef.current = data.access_token;
      // Update the httpOnly cookie with the new access token
      await fetch('/api/auth/set-cookie', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: data.access_token }),
      });
      return true;
    } catch {
      return false;
    } finally {
      isRefreshing.current = false;
    }
  }, []);

  // Auto-detect existing session on mount (REQ 7.1)
  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      // 1. Try to read the access token from the httpOnly cookie
      const cookieRes = await fetch('/api/auth/set-cookie');
      const { token } = (await cookieRes.json()) as { token: string | null };

      if (token) {
        memoryTokenRef.current = token;
      }

      // 2. No token at all — skip the /auth/me call entirely (avoids a noisy 401)
      if (!memoryTokenRef.current) {
        return;
      }

      // 3. Try /auth/me with the stored access token
      try {
        const apiUser = await apiClient.auth.me();
        if (cancelled) return;
        setUser({
          id: apiUser.id,
          email: apiUser.email,
          role: apiUser.role as UserRole,
          fullName: apiUser.fullName,
        });
        return;
      } catch (err) {
        // Access token may be expired — fall through to refresh attempt
        if ((err as { status?: number })?.status !== 401) throw err;
      }

      // 4. Access token expired — attempt silent refresh before giving up
      memoryTokenRef.current = null;
      const refreshed = await tryRefresh();
      if (cancelled) return;

      if (refreshed) {
        try {
          const apiUser = await apiClient.auth.me();
          if (cancelled) return;
          setUser({
            id: apiUser.id,
            email: apiUser.email,
            role: apiUser.role as UserRole,
            fullName: apiUser.fullName,
          });
        } catch {
          if (!cancelled) setUser(null);
        }
      }
      // if refresh also failed, user stays null (not logged in)
    }

    restoreSession()
      .catch(() => { if (!cancelled) setUser(null); })
      .finally(() => { if (!cancelled) setIsLoading(false); });

    return () => { cancelled = true; };
  }, [apiClient, tryRefresh]);

  /**
   * Wrapper around fetch that intercepts 401 responses, attempts a silent
   * token refresh, and replays the original request once. If the refresh
   * fails, the user is redirected to /login. (REQ 4.5, 7.3)
   */
  const fetchWithRefresh = useCallback(
    async (input: RequestInfo, init?: RequestInit): Promise<Response> => {
      // Inject current token into Authorization header
      const headers = new Headers(init?.headers);
      if (memoryTokenRef.current) {
        headers.set('Authorization', `Bearer ${memoryTokenRef.current}`);
      }

      const response = await fetch(input, { ...init, headers });

      if (response.status !== 401) return response;

      // 401 — try silent refresh
      const refreshed = await tryRefresh();
      if (!refreshed) {
        // Refresh failed — clear state and redirect to login (REQ 7.3)
        memoryTokenRef.current = null;
        setUser(null);
        await fetch('/api/auth/set-cookie', { method: 'DELETE' });
        router.push(`/${locale}/login`);
        return response;
      }

      // Replay the original request with the new token
      const retryHeaders = new Headers(init?.headers);
      if (memoryTokenRef.current) {
        retryHeaders.set('Authorization', `Bearer ${memoryTokenRef.current}`);
      }
      return fetch(input, { ...init, headers: retryHeaders });
    },
    [locale, router, tryRefresh],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const response = await apiClient.auth.login(email, password);

      // Store token in memory for subsequent API calls
      memoryTokenRef.current = response.access_token;

      // Persist token in httpOnly cookie via Next.js API route
      await fetch('/api/auth/set-cookie', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: response.access_token }),
      });

      // Use the user from the login response, or fall back to /auth/me
      let authUser: AuthUser;
      if (response.user) {
        authUser = {
          id: response.user.id,
          email: response.user.email,
          role: response.user.role as UserRole,
          fullName: response.user.fullName,
        };
      } else {
        const apiUser = await apiClient.auth.me();
        authUser = {
          id: apiUser.id,
          email: apiUser.email,
          role: apiUser.role as UserRole,
          fullName: apiUser.fullName,
        };
      }
      setUser(authUser);

      // Role-based redirect
      if (authUser.role === 'admin') {
        router.push(`/${locale}/admin`);
      } else {
        router.push(`/${locale}`);
      }
    },
    [apiClient, locale, router],
  );

  const logout = useCallback(async () => {
    try {
      await apiClient.auth.logout();
    } catch {
      // Ignore backend errors on logout
    } finally {
      memoryTokenRef.current = null;
      setUser(null);

      // Clear the httpOnly cookie
      await fetch('/api/auth/set-cookie', { method: 'DELETE' });

      router.push(`/${locale}/login`);
    }
  }, [apiClient, locale, router]);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, fetchWithRefresh, getToken }}>
      {children}
    </AuthContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside <AuthProvider>');
  }
  return ctx;
}
