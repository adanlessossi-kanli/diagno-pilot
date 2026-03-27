/**
 * Unit tests for AuthContext (security-hardened, cookie-based auth)
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4, 1.5
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import { AuthProvider, useAuth } from '../AuthContext';

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
  role: 'medecin' as const,
  locale: 'fr',
};

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  // Default: no active session on mount
  mockMe.mockRejectedValue(Object.assign(new Error('Unauthorized'), { status: 401 }));
  // Default: refresh fails so mount's tryRefresh doesn't consume extra mockMe values
  global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({}) });
});

describe('AuthContext — initial state', () => {
  it('isLoading is true until auth/me resolves', async () => {
    let resolveMe!: (v: typeof fakeUser) => void;
    mockMe.mockReturnValue(new Promise<typeof fakeUser>((res) => { resolveMe = res; }));

    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.isLoading).toBe(true);

    await act(async () => { resolveMe(fakeUser); });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
  });

  it('user is null when auth/me returns 401 on mount', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.user).toBeNull();
  });

  it('user is populated when auth/me succeeds on mount', async () => {
    mockMe.mockResolvedValue(fakeUser);
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.user).toMatchObject({ id: 'u1', email: 'doc@example.com' });
  });

  it('getToken is not exposed on context value (REQ 1.7)', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect((result.current as unknown as Record<string, unknown>)['getToken']).toBeUndefined();
  });
});

describe('AuthContext — login', () => {
  it('calls POST /api/v1/auth/login then GET /auth/me to populate user (REQ 3.1, 3.3)', async () => {
    mockLogin.mockResolvedValue({ token_type: 'bearer', expires_in: 900 });
    mockMe
      .mockRejectedValueOnce(Object.assign(new Error('no session'), { status: 401 })) // mount
      .mockResolvedValueOnce(fakeUser); // after login

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => { await result.current.login('doc@example.com', 'password'); });

    expect(mockLogin).toHaveBeenCalledWith('doc@example.com', 'password');
    expect(mockMe).toHaveBeenCalledTimes(2); // once on mount (fails), once after login
    expect(result.current.user).toMatchObject({ id: 'u1', role: 'medecin' });
  });

  it('does NOT call /api/auth/set-cookie BFF route (REQ 3.1)', async () => {
    mockLogin.mockResolvedValue({ token_type: 'bearer', expires_in: 900 });
    mockMe
      .mockRejectedValueOnce(Object.assign(new Error('no session'), { status: 401 }))
      .mockResolvedValueOnce(fakeUser);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => { await result.current.login('doc@example.com', 'password'); });

    const fetchCalls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls as [string][];
    const bffCalls = fetchCalls.filter(([url]) => typeof url === 'string' && url.includes('/api/auth/set-cookie'));
    expect(bffCalls).toHaveLength(0);
  });

  it('redirects admin to /fr/admin after login', async () => {
    mockLogin.mockResolvedValue({ token_type: 'bearer', expires_in: 900 });
    mockMe
      .mockRejectedValueOnce(Object.assign(new Error('no session'), { status: 401 }))
      .mockResolvedValueOnce({ ...fakeUser, role: 'admin' });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => { await result.current.login('admin@example.com', 'password'); });
    expect(mockPush).toHaveBeenCalledWith('/fr/admin');
  });

  it('redirects non-admin to locale root after login', async () => {
    mockLogin.mockResolvedValue({ token_type: 'bearer', expires_in: 900 });
    mockMe
      .mockRejectedValueOnce(Object.assign(new Error('no session'), { status: 401 }))
      .mockResolvedValueOnce(fakeUser);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => { await result.current.login('doc@example.com', 'password'); });
    expect(mockPush).toHaveBeenCalledWith('/fr');
  });
});

describe('AuthContext — logout', () => {
  it('calls POST /api/v1/auth/logout and clears user state (REQ 1.5)', async () => {
    mockLogout.mockResolvedValue(undefined);
    mockLogin.mockResolvedValue({ token_type: 'bearer', expires_in: 900 });
    mockMe
      .mockRejectedValueOnce(Object.assign(new Error('no session'), { status: 401 }))
      .mockResolvedValueOnce(fakeUser);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => { await result.current.login('doc@example.com', 'password'); });
    expect(result.current.user).not.toBeNull();

    await act(async () => { await result.current.logout(); });

    expect(mockLogout).toHaveBeenCalled();
    expect(result.current.user).toBeNull();
    expect(mockPush).toHaveBeenCalledWith('/fr/login');
  });

  it('does NOT call /api/auth/set-cookie DELETE on logout (REQ 3.1)', async () => {
    mockLogout.mockResolvedValue(undefined);
    mockMe.mockRejectedValue(Object.assign(new Error('no session'), { status: 401 }));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => { await result.current.logout(); });

    const fetchCalls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls as [string][];
    const bffCalls = fetchCalls.filter(([url]) => typeof url === 'string' && url.includes('/api/auth/set-cookie'));
    expect(bffCalls).toHaveLength(0);
  });
});

describe('AuthContext — fetchWithRefresh: 401 → refresh → retry (REQ 3.2)', () => {
  it('retries original request after successful silent refresh', async () => {
    mockMe.mockRejectedValue(Object.assign(new Error('no session'), { status: 401 }));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // After mount completes, set up fresh mocks for fetchWithRefresh
    // fetchMe uses apiClient.auth.me (mockMe), not global.fetch
    mockMe.mockResolvedValue(fakeUser); // for tryRefresh → fetchMe

    const mockFetch = vi.fn()
      // fetchWithRefresh: original request → 401
      .mockResolvedValueOnce({ status: 401, ok: false } as Response)
      // fetchWithRefresh: tryRefresh → POST /auth/refresh succeeds
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) } as Response)
      // fetchWithRefresh: retry original request → 200
      .mockResolvedValueOnce({ status: 200, ok: true } as Response);

    global.fetch = mockFetch;

    let response!: Response;
    await act(async () => {
      response = await result.current.fetchWithRefresh('http://localhost:8000/api/v1/patients');
    });

    expect(response.status).toBe(200);
  });

  it('does not inject Authorization header — uses credentials:include only (REQ 3.1)', async () => {
    mockMe.mockRejectedValue(Object.assign(new Error('no session'), { status: 401 }));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const mockFetch = vi.fn().mockResolvedValue({ status: 200, ok: true } as Response);
    global.fetch = mockFetch;

    await act(async () => {
      await result.current.fetchWithRefresh('http://localhost:8000/api/v1/patients');
    });

    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const authHeader = (init?.headers as Record<string, string> | undefined)?.['Authorization'];
    expect(authHeader).toBeUndefined();
    expect(init?.credentials).toBe('include');
  });
});

describe('AuthContext — fetchWithRefresh: double-401 → redirect (REQ 3.4)', () => {
  it('redirects to login and clears user when refresh fails', async () => {
    mockMe.mockRejectedValue(Object.assign(new Error('no session'), { status: 401 }));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const mockFetch = vi.fn()
      // fetchWithRefresh: original request → 401
      .mockResolvedValueOnce({ status: 401, ok: false } as Response)
      // fetchWithRefresh: tryRefresh → POST /auth/refresh fails
      .mockResolvedValueOnce({ ok: false, status: 401 } as Response);

    global.fetch = mockFetch;

    await act(async () => {
      await result.current.fetchWithRefresh('http://localhost:8000/api/v1/patients');
    });

    expect(result.current.user).toBeNull();
    expect(mockPush).toHaveBeenCalledWith('/fr/login');
  });

  it('redirects to login and clears user on double-401 (retry also 401)', async () => {
    mockMe.mockRejectedValue(Object.assign(new Error('no session'), { status: 401 }));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Simulate: refresh succeeds but retry still returns 401
    mockMe.mockResolvedValue(fakeUser); // fetchMe inside tryRefresh succeeds

    const mockFetch = vi.fn()
      // fetchWithRefresh: original request → 401
      .mockResolvedValueOnce({ status: 401, ok: false } as Response)
      // fetchWithRefresh: tryRefresh → POST /auth/refresh succeeds
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) } as Response)
      // fetchWithRefresh: retry original request → still 401
      .mockResolvedValueOnce({ status: 401, ok: false } as Response);

    global.fetch = mockFetch;

    let response!: Response;
    await act(async () => {
      response = await result.current.fetchWithRefresh('http://localhost:8000/api/v1/patients');
    });

    expect(response.status).toBe(401);
    expect(result.current.user).toBeNull();
    expect(mockPush).toHaveBeenCalledWith('/fr/login');
  });
});
