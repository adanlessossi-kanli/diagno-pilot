'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { createApiClient } from '@diagno-pilot/api-client';
import type { UserRole } from '@diagno-pilot/types';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AuthUser {
  id: string;
  email: string;
  role: UserRole;
  fullName: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

// ─── Context ──────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

// ─── Token management (in-memory, cookie set server-side) ────────────────────

let memoryToken: string | null = null;

function getToken(): string | null {
  return memoryToken;
}

function createClient() {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
  return createApiClient(baseUrl, getToken);
}

// ─── Provider ─────────────────────────────────────────────────────────────────

export function AuthProvider({ children, locale }: { children: React.ReactNode; locale: string }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  // Auto-detect existing session on mount
  useEffect(() => {
    const client = createClient();
    client.auth
      .me()
      .then((apiUser) => {
        setUser({
          id: apiUser.id,
          email: apiUser.email,
          role: apiUser.role as UserRole,
          fullName: apiUser.fullName,
        });
      })
      .catch(() => {
        // No active session — that's fine
        setUser(null);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const client = createClient();
      const response = await client.auth.login(email, password);

      // Store token in memory for subsequent API calls
      memoryToken = response.access_token;

      // Persist token in httpOnly cookie via Next.js API route
      await fetch('/api/auth/set-cookie', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: response.access_token }),
      });

      const authUser: AuthUser = {
        id: response.user.id,
        email: response.user.email,
        role: response.user.role as UserRole,
        fullName: response.user.fullName,
      };
      setUser(authUser);

      // Role-based redirect
      if (authUser.role === 'admin') {
        router.push(`/${locale}/admin`);
      } else {
        router.push(`/${locale}`);
      }
    },
    [locale, router],
  );

  const logout = useCallback(async () => {
    try {
      const client = createClient();
      await client.auth.logout();
    } catch {
      // Ignore backend errors on logout
    } finally {
      memoryToken = null;
      setUser(null);

      // Clear the httpOnly cookie
      await fetch('/api/auth/set-cookie', { method: 'DELETE' });

      router.push(`/${locale}/login`);
    }
  }, [locale, router]);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
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
