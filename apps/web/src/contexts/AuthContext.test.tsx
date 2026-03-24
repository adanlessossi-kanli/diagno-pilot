/**
 * Unit tests for AuthContext
 * Validates: Requirements REQ-01 (login/logout, token persistence, role-based redirect)
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
  // Default: fetch succeeds (cookie API route)
  global.fetch = vi.fn().mockResolvedValue({ ok: true });
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
});
