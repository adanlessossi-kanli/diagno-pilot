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

  const apiClient = React.useMemo(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
    return createApiClient(baseUrl);
  }, []);

  /**
   * Fetch the current user from /auth/me and update state.
   * Returns the AuthUser on success, or null on failure.
   */
  const fetchMe = useCallback(async (): Promise<AuthUser | null> => {
    try {
      const apiUser = await apiClient.auth.me();
      const authUser: AuthUser = {
        id: apiUser.id,
        email: apiUser.email,
        role: apiUser.role as UserRole,
        fullName: apiUser.fullName,
      };
      setUser(authUser);
      return authUser;
    } catch {
      setUser(null);
      return null;
    }
  }, [apiClient]);

  /**
   * Attempt a silent token refresh via POST /api/v1/auth/refresh.
   * Returns true if refresh succeeded (cookies rotated), false otherwise.
   * On success, re-calls GET /auth/me to refresh user state. (REQ 3.2, 7.2)
   */
  const tryRefresh = useCallback(async (): Promise<boolean> => {
    if (isRefreshing.current) return false;
    isRefreshing.current = true;
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
      const res = await fetch(`${baseUrl}/api/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!res.ok) return false;
      // Re-fetch user state with the new cookies (REQ 7.2)
      await fetchMe();
      return true;
    } catch {
      return false;
    } finally {
      isRefreshing.current = false;
    }
  }, [fetchMe]);

  // Auto-detect existing session on mount — auth state determined by GET /auth/me (REQ 3.3)
  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      // Always try /auth/me — the access_token cookie is HttpOnly so
      // document.cookie cannot see it, but the browser sends it automatically.
      try {
        const apiUser = await apiClient.auth.me();
        if (cancelled) return;
        setUser({
          id: apiUser.id,
          email: apiUser.email,
          role: apiUser.role as UserRole,
          fullName: apiUser.fullName,
        });
      } catch (err) {
        if (cancelled) return;
        // If 401, attempt silent refresh before giving up
        if ((err as { status?: number })?.status === 401) {
          const refreshed = await tryRefresh();
          if (cancelled) return;
          if (!refreshed) {
            setUser(null);
          }
          // If refreshed, fetchMe() inside tryRefresh already updated user state
        } else {
          setUser(null);
        }
      }
    }

    restoreSession()
      .catch(() => { if (!cancelled) setUser(null); })
      .finally(() => { if (!cancelled) setIsLoading(false); });

    return () => { cancelled = true; };
  }, [apiClient, tryRefresh]);

  /**
   * Wrapper around fetch that intercepts 401 responses, attempts a silent
   * token refresh, and replays the original request once.
   * On double-401, redirects to login and clears local auth state. (REQ 3.2, 3.4)
   * No Authorization header injection — cookies are automatic.
   */
  const fetchWithRefresh = useCallback(
    async (input: RequestInfo, init?: RequestInit): Promise<Response> => {
      // No Authorization header injection — cookies are sent automatically
      const response = await fetch(input, { ...init, credentials: 'include' });

      if (response.status !== 401) return response;

      // 401 — try silent refresh
      const refreshed = await tryRefresh();
      if (!refreshed) {
        // Refresh failed — clear state and redirect to login (REQ 3.4)
        setUser(null);
        router.push(`/${locale}/login`);
        return response;
      }

      // Replay the original request — cookies are now updated
      const retryResponse = await fetch(input, { ...init, credentials: 'include' });

      if (retryResponse.status === 401) {
        // Double-401 — clear state and redirect to login (REQ 3.4)
        setUser(null);
        router.push(`/${locale}/login`);
      }

      return retryResponse;
    },
    [locale, router, tryRefresh],
  );

  /**
   * Login: POST /api/v1/auth/login with credentials:include, then GET /auth/me. (REQ 3.1, 3.3)
   */
  const login = useCallback(
    async (email: string, password: string) => {
      // apiClient.auth.login already sends credentials:'include' and handles CSRF
      await apiClient.auth.login(email, password);

      // Populate user state from /auth/me (REQ 3.3)
      const authUser = await fetchMe();
      if (!authUser) {
        throw new Error('Failed to retrieve user after login');
      }

      router.push(`/${locale}`);
    },
    [apiClient, fetchMe, locale, router],
  );

  /**
   * Logout: POST /api/v1/auth/logout with credentials:include, clear local user state. (REQ 1.5)
   */
  const logout = useCallback(async () => {
    try {
      await apiClient.auth.logout();
    } catch {
      // Ignore backend errors on logout
    } finally {
      setUser(null);
      router.push(`/${locale}/login`);
    }
  }, [apiClient, locale, router]);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, fetchWithRefresh }}>
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
