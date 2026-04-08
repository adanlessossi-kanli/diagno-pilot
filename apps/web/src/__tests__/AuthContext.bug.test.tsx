/**
 * Bug condition exploration tests — AuthContext redirect bug
 *
 * These tests assert the EXPECTED (correct) behavior and will FAIL on unfixed
 * code, proving the bug exists. DO NOT fix the code when these fail.
 *
 * **Validates: Requirements 1.9, 2.9**
 *
 * Bug confirmed by this file:
 *   - Bug 1.9: After login, admin users are redirected to /${locale}/admin
 *     instead of /${locale} (Accueil). The fix should redirect ALL roles to /${locale}.
 *
 * Counterexamples found (documented after running on unfixed code):
 *   - role='admin' → router.push called with '/fr/admin' instead of '/fr'
 *   - role='medecin' → router.push called with '/fr' (already correct)
 *   - role='guest' → router.push called with '/fr' (already correct)
 *   - role='infirmière' → router.push called with '/fr' (already correct)
 *   The property fails for role='admin' specifically.
 */

import fc from 'fast-check';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import { AuthProvider, useAuth } from '../contexts/AuthContext';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
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

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  // Default: no active session on mount
  mockMe.mockRejectedValue(Object.assign(new Error('Unauthorized'), { status: 401 }));
  // Default: refresh fails
  global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({}) });
  // Clear cookies between tests
  document.cookie = 'access_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

// ─── Bug 1.9: Admin redirect goes to /fr/admin instead of /fr ────────────────

describe('Bug 1.9 — Wrong post-login redirect for admin', () => {
  /**
   * **Validates: Requirements 1.9, 2.9**
   * After login, ALL roles MUST be redirected to /${locale} (Accueil).
   * EXPECTED TO FAIL on unfixed code for admin role — admin is redirected to /${locale}/admin.
   * Counterexample: role='admin' → router.push('/fr/admin') instead of router.push('/fr').
   */
  it('admin login redirects to /fr (not /fr/admin)', async () => {
    mockLogin.mockResolvedValue({ token_type: 'bearer', expires_in: 900 });
    mockMe
      .mockRejectedValueOnce(Object.assign(new Error('no session'), { status: 401 })) // mount
      .mockResolvedValueOnce({
        id: 'admin1',
        email: 'admin@test.com',
        fullName: 'Admin',
        role: 'admin',
        locale: 'fr',
      }); // after login

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.login('admin@test.com', 'password');
    });

    // BUG 1.9: on unfixed code, admin is pushed to '/fr/admin' not '/fr'
    expect(mockPush).toHaveBeenCalledWith('/fr');
    expect(mockPush).not.toHaveBeenCalledWith('/fr/admin');
  });

  it('medecin login redirects to /fr (already correct, baseline)', async () => {
    mockLogin.mockResolvedValue({ token_type: 'bearer', expires_in: 900 });
    mockMe
      .mockRejectedValueOnce(Object.assign(new Error('no session'), { status: 401 })) // mount
      .mockResolvedValueOnce({
        id: 'doc1',
        email: 'doc@test.com',
        fullName: 'Dr Test',
        role: 'medecin',
        locale: 'fr',
      }); // after login

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.login('doc@test.com', 'password');
    });

    expect(mockPush).toHaveBeenCalledWith('/fr');
  });
});

// ─── Property: ALL roles redirect to /fr after login ─────────────────────────

describe('Bug 1.9 — Property: all roles redirect to /${locale} after login', () => {
  /**
   * **Validates: Requirements 1.9, 2.9**
   * For ANY role, login() MUST call router.push with '/${locale}' (not role-branched).
   * EXPECTED TO FAIL on unfixed code for role='admin'.
   * Counterexample: role='admin' → router.push('/fr/admin') ≠ '/fr'.
   */
  it('for any role, router.push is called with /fr after login', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom('admin', 'medecin', 'guest', 'infirmière'),
        async (role) => {
          vi.clearAllMocks();
          mockMe.mockRejectedValue(Object.assign(new Error('Unauthorized'), { status: 401 }));
          global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({}) });
          document.cookie = 'access_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT';

          mockLogin.mockResolvedValue({ token_type: 'bearer', expires_in: 900 });
          mockMe
            .mockRejectedValueOnce(Object.assign(new Error('no session'), { status: 401 })) // mount
            .mockResolvedValueOnce({
              id: 'user1',
              email: `${role}@test.com`,
              fullName: 'Test User',
              role,
              locale: 'fr',
            }); // after login

          const { result, unmount } = renderHook(() => useAuth(), { wrapper });
          await waitFor(() => expect(result.current.isLoading).toBe(false));

          await act(async () => {
            await result.current.login(`${role}@test.com`, 'password');
          });

          const pushCalls = mockPush.mock.calls as string[][];
          const pushedTo = pushCalls[pushCalls.length - 1]?.[0] ?? '';

          unmount();

          // BUG 1.9: admin role pushes to '/fr/admin' on unfixed code
          // Expected: ALL roles push to '/fr'
          return pushedTo === '/fr';
        },
      ),
      { numRuns: 4 },
    );
  });
});
