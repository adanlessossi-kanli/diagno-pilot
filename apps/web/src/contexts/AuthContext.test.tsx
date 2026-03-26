/**
 * Unit tests for AuthContext
 * Validates: Requirements REQ-01, 4.5, 7.1, 7.2, 7.3
 * (login/logout, token persistence, role-based redirect, fetchWithRefresh, isLoading)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import { AuthProvider, useAuth } from './AuthContext';

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
  locale: 'fr',
};

const fakeLoginResponse = {
  access_token: 'tok123',
  token_type: 'bearer',
  user: fakeUser,
};

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  // Default: no active session on mount
  mockMe.mockRejectedValue(new Error('Unauthorized'));
  // Default: fetch handles cookie GET (returns null token) and other calls (returns ok: true)
  global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (typeof url === 'string' && url.includes('/api/auth/set-cookie') && (!init?.method || init.method === 'GET')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ token: null }),
      });
    }
    return Promise.resolve({ ok: true, json: async () => ({}) });
  });
});

describe('AuthContext', () => {
  it('a. login success — sets user and calls fetch to set cookie', async () => {
    mockMe.mockRejectedValue(new Error('no session'));
    mockLogin.mockResolvedValue(fakeLoginResponse);

    const { result } = renderHook(() => useAuth(), { wrapper });

    // Wait for initial loading to finish
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

  it('b. login failure — rejects and user stays null', async () => {
    mockMe.mockRejectedValue(new Error('no session'));
    mockLogin.mockRejectedValue(new Error('Invalid credentials'));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await expect(
      act(async () => {
        await result.current.login('bad@example.com', 'wrong');
      }),
    ).rejects.toThrow('Invalid credentials');

    expect(result.current.user).toBeNull();
  });

  it('c. logout — clears user and calls DELETE on cookie route', async () => {
    mockMe.mockRejectedValue(new Error('no session'));
    mockLogin.mockResolvedValue(fakeLoginResponse);
    mockLogout.mockResolvedValue(undefined);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Login first
    await act(async () => {
      await result.current.login('doc@example.com', 'password');
    });
    expect(result.current.user).not.toBeNull();

    // Now logout
    await act(async () => {
      await result.current.logout();
    });

    expect(result.current.user).toBeNull();
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/auth/set-cookie',
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('d. session persistence on mount — user populated from auth.me()', async () => {
    mockMe.mockResolvedValue(fakeUser);
    // Provide a token so restoreSession proceeds to call auth.me()
    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (typeof url === 'string' && url.includes('/api/auth/set-cookie') && (!init?.method || init.method === 'GET')) {
        return Promise.resolve({ ok: true, json: async () => ({ token: 'tok123' }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

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
    mockMe.mockRejectedValue(new Error('Unauthorized'));

    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.user).toBeNull();
    expect(result.current.isLoading).toBe(false);
  });

  /**
   * Validates: Requirement 9.4
   * WHEN a user is not authenticated and auth/me returns a 401,
   * THE system SHALL set user to null (and isLoading becomes false).
   */
  it('AuthContext sets user to null on 401 from auth/me', async () => {
    // Simulate auth/me returning a 401 Unauthorized response
    mockMe.mockRejectedValue(Object.assign(new Error('Unauthorized'), { status: 401 }));

    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.user).toBeNull();
  });

  it('f. role-based redirect — admin goes to /fr/admin', async () => {
    mockMe.mockRejectedValue(new Error('no session'));
    mockLogin.mockResolvedValue({
      ...fakeLoginResponse,
      user: { ...fakeUser, role: 'admin' },
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.login('admin@example.com', 'password');
    });

    expect(mockPush).toHaveBeenCalledWith(expect.stringContaining('/admin'));
  });

  it('f. role-based redirect — medecin goes to locale root', async () => {
    mockMe.mockRejectedValue(new Error('no session'));
    mockLogin.mockResolvedValue(fakeLoginResponse); // role: 'medecin'

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.login('doc@example.com', 'password');
    });

    // Should push to locale root, not /admin
    const calls = mockPush.mock.calls;
    expect(calls.length).toBeGreaterThan(0);
    const lastCall = calls[calls.length - 1][0] as string;
    expect(lastCall).not.toContain('/admin');
    expect(lastCall).toMatch(/^\/fr/);
  });

  it('g. isLoading is true until auth/me resolves (REQ 7.2)', async () => {
    let resolveMe!: (v: typeof fakeUser) => void;
    mockMe.mockReturnValue(new Promise<typeof fakeUser>((res) => { resolveMe = res; }));

    const { result } = renderHook(() => useAuth(), { wrapper });

    // Still loading before /auth/me resolves
    expect(result.current.isLoading).toBe(true);

    await act(async () => { resolveMe(fakeUser); });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
  });

  it('h. fetchWithRefresh — replays request after successful silent refresh (REQ 4.5)', async () => {
    mockMe.mockRejectedValue(new Error('no session'));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // First call returns 401, refresh returns new token, retry returns 200
    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ status: 401, ok: false } as Response)          // original request → 401
      .mockResolvedValueOnce({ ok: true, json: async () => ({ access_token: 'new-tok' }) } as Response) // /auth/refresh
      .mockResolvedValueOnce({ ok: true, json: async () => ({ access_token: 'new-tok' }) } as Response) // set-cookie
      .mockResolvedValueOnce({ status: 200, ok: true } as Response);          // replayed request

    global.fetch = mockFetch;

    let response!: Response;
    await act(async () => {
      response = await result.current.fetchWithRefresh('http://localhost:8000/api/v1/patients');
    });

    expect(response.status).toBe(200);
  });

  it('i. fetchWithRefresh — redirects to login if refresh fails (REQ 7.3)', async () => {
    mockMe.mockRejectedValue(new Error('no session'));

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const mockFetch = vi.fn()
      .mockResolvedValueOnce({ status: 401, ok: false } as Response)   // original → 401
      .mockResolvedValueOnce({ ok: false, status: 401 } as Response)   // /auth/refresh fails
      .mockResolvedValueOnce({ ok: true } as Response);                // set-cookie DELETE

    global.fetch = mockFetch;

    await act(async () => {
      await result.current.fetchWithRefresh('http://localhost:8000/api/v1/patients');
    });

    expect(result.current.user).toBeNull();
    expect(mockPush).toHaveBeenCalledWith(expect.stringContaining('/login'));
  });
});
