/**
 * Unit tests + Property-based tests for AuthContext (App_Web)
 * Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.8, 4.9, 7.7
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import * as fc from 'fast-check';
import { AuthProvider, useAuth } from '../AuthContext';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
const mockReplace = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
}));

const mockLogin = vi.fn();
const mockLogout = vi.fn();
const mockMe = vi.fn();

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    auth: {
      login: mockLogin,
      logout: mockLogout,
      me: mockMe,
    },
  }),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

function wrapper({ children }: { children: React.ReactNode }) {
  return <AuthProvider locale="fr">{children}</AuthProvider>;
}

const fakeUser = {
  id: 'u1',
  email: 'doc@example.com',
  fullName: 'Dr. Test',
  role: 'medecin',
};

const fakeAdminUser = {
  id: 'a1',
  email: 'admin@example.com',
  fullName: 'Admin User',
  role: 'admin',
};

function makeLoginResponse(user: { id: string; email: string; fullName: string; role: string }) {
  return { access_token: 'tok123', token_type: 'bearer', user };
}

function resetMocks(userForMe?: { id: string; email: string; fullName: string; role: string } | null) {
  vi.resetAllMocks();
  if (userForMe) {
    mockMe.mockResolvedValue(userForMe);
  } else {
    mockMe.mockRejectedValue(new Error('Unauthorized'));
  }
  global.fetch = vi.fn().mockResolvedValue({ ok: true });
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  resetMocks(null);
});

// ─── Unit Tests (8.2) ─────────────────────────────────────────────────────────

describe('AuthContext — Unit Tests', () => {
  it('login success — sets user and persists token via cookie', async () => {
    mockLogin.mockResolvedValue(makeLoginResponse(fakeUser));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.login('doc@example.com', 'password');
    });

    expect(result.current.user).toEqual({
      id: 'u1',
      email: 'doc@example.com',
      fullName: 'Dr. Test',
      role: 'medecin',
    });
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/auth/set-cookie',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('login failure — rejects with error, user stays null', async () => {
    mockLogin.mockRejectedValue(new Error('Invalid credentials'));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await expect(
      act(async () => {
        await result.current.login('bad@example.com', 'wrong');
      }),
    ).rejects.toThrow();

    expect(result.current.user).toBeNull();
  });

  it('logout — clears user, deletes cookie, redirects to /login', async () => {
    mockLogin.mockResolvedValue(makeLoginResponse(fakeUser));
    mockLogout.mockResolvedValue(undefined);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.login('doc@example.com', 'password');
    });
    expect(result.current.user).not.toBeNull();

    await act(async () => {
      await result.current.logout();
    });

    expect(result.current.user).toBeNull();
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/auth/set-cookie',
      expect.objectContaining({ method: 'DELETE' }),
    );
    expect(mockPush).toHaveBeenCalledWith(expect.stringContaining('/login'));
  });

  it('role-based redirect — admin role redirects to /admin', async () => {
    mockLogin.mockResolvedValue(makeLoginResponse(fakeAdminUser));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.login('admin@example.com', 'password');
    });

    expect(mockPush).toHaveBeenCalledWith(expect.stringContaining('/admin'));
  });

  it('role-based redirect — non-admin role redirects to locale root', async () => {
    mockLogin.mockResolvedValue(makeLoginResponse(fakeUser));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.login('doc@example.com', 'password');
    });

    const lastCall = mockPush.mock.calls[mockPush.mock.calls.length - 1][0] as string;
    expect(lastCall).not.toContain('/admin');
    expect(lastCall).toMatch(/^\/fr/);
  });

  it('session persistence — user restored from auth.me() on mount (httpOnly cookie)', async () => {
    mockMe.mockResolvedValue(fakeUser);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.user).toEqual({
      id: 'u1',
      email: 'doc@example.com',
      fullName: 'Dr. Test',
      role: 'medecin',
    });
  });

  it('refresh token — silent renewal replays request after 401', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ status: 401, ok: false } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ access_token: 'new-tok' }) } as Response)
      .mockResolvedValueOnce({ ok: true } as Response)
      .mockResolvedValueOnce({ status: 200, ok: true } as Response);

    global.fetch = mockFetch;

    let response!: Response;
    await act(async () => {
      response = await result.current.fetchWithRefresh('http://localhost:8000/api/v1/patients');
    });

    expect(response.status).toBe(200);
  });

  it('forced logout — redirects to /login if refresh fails', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ status: 401, ok: false } as Response)
      .mockResolvedValueOnce({ ok: false, status: 401 } as Response)
      .mockResolvedValueOnce({ ok: true } as Response);

    global.fetch = mockFetch;

    await act(async () => {
      await result.current.fetchWithRefresh('http://localhost:8000/api/v1/patients');
    });

    expect(result.current.user).toBeNull();
    expect(mockPush).toHaveBeenCalledWith(expect.stringContaining('/login'));
  });
});

// ─── Property Tests ───────────────────────────────────────────────────────────

// Feature: app-consistency, Property 2: Pour toute erreur, le message ne contient ni stack trace ni détail interne
describe('P2 — Error messages contain no technical details', () => {
  it('any error from login must not expose stack trace or internal details', { timeout: 30000 }, async () => {
    // Validates: Requirements 1.2, 1.4
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 30 }),
        fc.string({ minLength: 1, maxLength: 30 }),
        async (email, password) => {
          resetMocks(null);
          mockLogin.mockRejectedValue(new Error('Identifiants invalides'));

          const { result } = renderHook(() => useAuth(), { wrapper });
          await waitFor(() => expect(result.current.isLoading).toBe(false));

          let errorMessage = '';
          try {
            await act(async () => {
              await result.current.login(email, password);
            });
          } catch (e) {
            errorMessage = (e as Error).message;
          }

          // The first line of the error message must not be a stack trace frame
          const firstLine = errorMessage.split('\n')[0];
          expect(firstLine).not.toMatch(/^\s+at\s+\w+/);
          expect(firstLine).not.toMatch(/\.tsx?:\d+:\d+/);
          expect(firstLine).not.toMatch(/TypeError:|ReferenceError:|SyntaxError:/);

          return true;
        },
      ),
      { numRuns: 100 },
    );
  });
});

// Feature: app-consistency, Property 10: Pour tout utilisateur valide, redirection selon rôle
describe('P10 — Successful login redirects by role', () => {
  it('any valid user login must redirect to /admin for admin role, or / for others', { timeout: 60000 }, async () => {
    // Validates: Requirements 4.1, 4.8, 4.9
    const roles = ['admin', 'medecin', 'infirmier', 'pharmacien'];

    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom(...roles),
        fc.uuid(),
        async (role, id) => {
          resetMocks(null);

          const user = { id, email: `user-${id.slice(0, 8)}@example.com`, fullName: 'Test User', role };
          mockLogin.mockResolvedValue(makeLoginResponse(user));

          const { result } = renderHook(() => useAuth(), { wrapper });
          await waitFor(() => expect(result.current.isLoading).toBe(false));

          await act(async () => {
            await result.current.login(user.email, 'password123');
          });

          const calls = mockPush.mock.calls;
          expect(calls.length).toBeGreaterThan(0);
          const redirectTarget = calls[calls.length - 1][0] as string;

          if (role === 'admin') {
            expect(redirectTarget).toContain('/admin');
          } else {
            expect(redirectTarget).not.toContain('/admin');
          }

          return true;
        },
      ),
      { numRuns: 100 },
    );
  });
});

// Feature: app-consistency, Property 11: Pour tout couple email/mdp invalide, message générique sans révéler lequel est incorrect
describe('P11 — Generic error message for invalid credentials', () => {
  it('error message must not reveal whether email or password is wrong', { timeout: 30000 }, async () => {
    // Validates: Requirement 4.2
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 30 }),
        fc.string({ minLength: 1, maxLength: 30 }),
        async (email, password) => {
          resetMocks(null);
          mockLogin.mockRejectedValue(new Error('Identifiants invalides'));

          const { result } = renderHook(() => useAuth(), { wrapper });
          await waitFor(() => expect(result.current.isLoading).toBe(false));

          let errorMessage = '';
          try {
            await act(async () => {
              await result.current.login(email, password);
            });
          } catch (e) {
            errorMessage = (e as Error).message;
          }

          const lowerMsg = errorMessage.toLowerCase();
          expect(lowerMsg).not.toMatch(/email.*incorrect|incorrect.*email/);
          expect(lowerMsg).not.toMatch(/password.*incorrect|incorrect.*password/);
          expect(lowerMsg).not.toMatch(/mot de passe.*incorrect|incorrect.*mot de passe/);

          return true;
        },
      ),
      { numRuns: 100 },
    );
  });
});

// Feature: app-consistency, Property 12: Après déconnexion, token effacé et redirection /login
describe('P12 — After logout, token cleared and redirect to /login', () => {
  it('any authenticated user after logout must have token cleared and be redirected to /login', { timeout: 60000 }, async () => {
    // Validates: Requirement 4.3
    const roles = ['admin', 'medecin', 'infirmier'];

    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom(...roles),
        fc.uuid(),
        async (role, id) => {
          resetMocks(null);

          const user = { id, email: `user-${id.slice(0, 8)}@example.com`, fullName: 'Test', role };
          mockLogin.mockResolvedValue(makeLoginResponse(user));
          mockLogout.mockResolvedValue(undefined);

          const { result } = renderHook(() => useAuth(), { wrapper });
          await waitFor(() => expect(result.current.isLoading).toBe(false));

          await act(async () => {
            await result.current.login(user.email, 'password');
          });
          expect(result.current.user).not.toBeNull();

          const fetchMock = vi.fn().mockResolvedValue({ ok: true });
          global.fetch = fetchMock;

          await act(async () => {
            await result.current.logout();
          });

          expect(result.current.user).toBeNull();
          expect(fetchMock).toHaveBeenCalledWith(
            '/api/auth/set-cookie',
            expect.objectContaining({ method: 'DELETE' }),
          );
          expect(mockPush).toHaveBeenCalledWith(expect.stringContaining('/login'));

          return true;
        },
      ),
      { numRuns: 100 },
    );
  });
});

// Feature: app-consistency, Property 13: Après rechargement, session restaurée sans nouvelle connexion
describe('P13 — After page reload, session restored without new login', () => {
  it('any authenticated user session must be restored from httpOnly cookie on mount', { timeout: 60000 }, async () => {
    // Validates: Requirements 4.6, 4.7
    const roles = ['admin', 'medecin', 'infirmier'];

    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom(...roles),
        fc.uuid(),
        async (role, id) => {
          vi.resetAllMocks();
          global.fetch = vi.fn().mockResolvedValue({ ok: true });

          const user = { id, email: `user-${id.slice(0, 8)}@example.com`, fullName: 'Test User', role };
          mockMe.mockResolvedValue(user);

          const { result } = renderHook(() => useAuth(), { wrapper });
          await waitFor(() => expect(result.current.isLoading).toBe(false));

          expect(result.current.user).not.toBeNull();
          expect(result.current.user?.id).toBe(id);
          expect(result.current.user?.role).toBe(role);
          expect(mockLogin).not.toHaveBeenCalled();

          return true;
        },
      ),
      { numRuns: 100 },
    );
  });
});

// Feature: app-consistency, Property 1: Pour toute opération async > 300ms, un indicateur de chargement est présent
describe('P1 — Loading indicator present during async operations', () => {
  it('isLoading is true while auth.me() is pending, indicating a loading state', { timeout: 120000 }, async () => {
    // Validates: Requirements 1.1, 1.3
    // Property 1: For any async operation exceeding 300ms, a loading indicator must be present.
    // We verify that AuthContext exposes isLoading=true during the async me() call,
    // which consumers (SkeletonLoader, spinners) use to display loading feedback.
    const roles = ['admin', 'medecin', 'infirmier', 'pharmacien'];

    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom(...roles),
        fc.uuid(),
        // Keep delay small (10-50ms) to avoid timeout while still testing async behavior
        fc.integer({ min: 10, max: 50 }),
        async (role, id, delayMs) => {
          vi.resetAllMocks();
          global.fetch = vi.fn().mockResolvedValue({ ok: true });

          const user = { id, email: `user-${id.slice(0, 8)}@example.com`, fullName: 'Test User', role };

          // Simulate an async operation (the delay represents > 300ms in production)
          mockMe.mockImplementation(
            () => new Promise((resolve) => setTimeout(() => resolve(user), delayMs)),
          );

          const { result } = renderHook(() => useAuth(), { wrapper });

          // Immediately after mount, isLoading must be true (loading indicator present)
          expect(result.current.isLoading).toBe(true);

          // Wait for the async operation to complete
          await waitFor(() => expect(result.current.isLoading).toBe(false), {
            timeout: delayMs + 500,
          });

          // After completion, user is set and isLoading is false
          expect(result.current.user).not.toBeNull();
          expect(result.current.user?.id).toBe(id);

          return true;
        },
      ),
      { numRuns: 100 },
    );
  });
});
