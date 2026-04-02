/**
 * Unit tests for AuthContext (legacy location — kept for backward compatibility)
 * These tests validate the cookie-based auth flow after security hardening.
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4, 1.5, 1.7
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import { AuthProvider, useAuth } from './AuthContext';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockLogin = vi.fn();
const mockLogout = vi.fn();
const mockMe = vi.fn();

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    auth: { login: mockLogin, logout: mockLogout, me: mockMe },
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
  locale: 'fr',
};

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  mockMe.mockRejectedValue(Object.assign(new Error('Unauthorized'), { status: 401 }));
  // Default: refresh fails so mount's tryRefresh doesn't consume extra mockMe values
  global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({}) });
});

describe('AuthContext', () => {
  it('a. login success — sets user via /auth/me (REQ 3.3)', async () => {
    mockLogin.mockResolvedValue({ token_type: 'bearer', expires_in: 900 });
    mockMe
      .mockRejectedValueOnce(Object.assign(new Error('no session'), { status: 401 }))
      .mockResolvedValueOnce(fakeUser);

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
  });

  it('b. login does NOT call /api/auth/set-cookie BFF route (REQ 3.1)', async () => {
    mockLogin.mockResolvedValue({ token_type: 'bearer', expires_in: 900 });
    mockMe
      .mockRejectedValueOnce(Object.assign(new Error('no session'), { status: 401 }))
      .mockResolvedValueOnce(fakeUser);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.login('doc@example.com', 'password');
    });

    const fetchCalls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls as [string][];
    const bffCalls = fetchCalls.filter(([url]) => typeof url === 'string' && url.includes('/api/auth/set-cookie'));
    expect(bffCalls).toHaveLength(0);
  });

  it('c. logout — clears user and does NOT call /api/auth/set-cookie DELETE (REQ 1.5, 3.1)', async () => {
    mockLogout.mockResolvedValue(undefined);
    mockMe.mockRejectedValue(Object.assign(new Error('no session'), { status: 401 }));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => { await result.current.logout(); });

    expect(result.current.user).toBeNull();
    expect(mockPush).toHaveBeenCalledWith('/fr/login');

    const fetchCalls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls as [string][];
    const bffCalls = fetchCalls.filter(([url]) => typeof url === 'string' && url.includes('/api/auth/set-cookie'));
    expect(bffCalls).toHaveLength(0);
  });

  it('d. session persistence on mount — user populated from auth.me() (REQ 3.3)', async () => {
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

  it('e. no session on mount — user is null and isLoading becomes false', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.user).toBeNull();
  });

  it('f. getToken is not exposed on context value (REQ 1.7)', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect((result.current as unknown as Record<string, unknown>)['getToken']).toBeUndefined();
  });

  it('g. role-based redirect — admin goes to /fr', async () => {
    mockLogin.mockResolvedValue({ token_type: 'bearer', expires_in: 900 });
    mockMe
      .mockRejectedValueOnce(Object.assign(new Error('no session'), { status: 401 }))
      .mockResolvedValueOnce({ ...fakeUser, role: 'admin' });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => { await result.current.login('admin@example.com', 'password'); });
    expect(mockPush).toHaveBeenCalledWith('/fr');
  });

  it('h. isLoading is true until auth/me resolves (REQ 7.2)', async () => {
    let resolveMe!: (v: typeof fakeUser) => void;
    mockMe.mockReturnValue(new Promise<typeof fakeUser>((res) => { resolveMe = res; }));

    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.isLoading).toBe(true);

    await act(async () => { resolveMe(fakeUser); });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
  });

  it('i. fetchWithRefresh — replays request after successful silent refresh (REQ 3.2)', async () => {
    mockMe
      .mockRejectedValueOnce(Object.assign(new Error('no session'), { status: 401 })) // mount
      .mockResolvedValue(fakeUser); // tryRefresh → fetchMe

    const { result } = renderHook(() => useAuth(), { wrapper });

    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401 } as Response) // mount tryRefresh fails
      .mockResolvedValueOnce({ status: 401, ok: false } as Response) // original request → 401
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) } as Response) // /auth/refresh
      .mockResolvedValueOnce({ status: 200, ok: true } as Response); // retry

    global.fetch = mockFetch;

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let response!: Response;
    await act(async () => {
      response = await result.current.fetchWithRefresh('http://localhost:8000/api/v1/patients');
    });

    expect(response.status).toBe(200);
  });

  it('j. fetchWithRefresh — redirects to login if refresh fails (REQ 3.4)', async () => {
    mockMe.mockRejectedValue(Object.assign(new Error('no session'), { status: 401 }));

    const { result } = renderHook(() => useAuth(), { wrapper });

    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401 } as Response) // mount tryRefresh fails
      .mockResolvedValueOnce({ status: 401, ok: false } as Response) // original → 401
      .mockResolvedValueOnce({ ok: false, status: 401 } as Response); // /auth/refresh fails

    global.fetch = mockFetch;

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.fetchWithRefresh('http://localhost:8000/api/v1/patients');
    });

    expect(result.current.user).toBeNull();
    expect(mockPush).toHaveBeenCalledWith(expect.stringContaining('/login'));
  });
});
