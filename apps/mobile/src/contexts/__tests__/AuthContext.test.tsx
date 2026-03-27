/**
 * Unit tests for mobile AuthContext — session restoration (REQ 7.4, 10.3)
 *
 * Covers:
 *  a. Session restored from SecureStore on startup
 *  b. SecureStore empty → user stays null, isLoading becomes false
 *  c. /auth/me returns 401 → token cleared, user stays null
 */
import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react-native';
import { AuthProvider, useAuth, TOKEN_KEY } from '../AuthContext';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockGetItemAsync = jest.fn();
const mockSetItemAsync = jest.fn();
const mockDeleteItemAsync = jest.fn();

jest.mock('expo-secure-store', () => ({
  getItemAsync: (...args: unknown[]) => mockGetItemAsync(...args),
  setItemAsync: (...args: unknown[]) => mockSetItemAsync(...args),
  deleteItemAsync: (...args: unknown[]) => mockDeleteItemAsync(...args),
}));

const mockMe = jest.fn();
const mockLogin = jest.fn();
const mockLogout = jest.fn();

jest.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    auth: {
      me: mockMe,
      login: mockLogin,
      logout: mockLogout,
    },
  }),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

function wrapper({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

const fakeUser = {
  id: 'u1',
  email: 'doc@example.com',
  fullName: 'Dr. Test',
  role: 'medecin',
};

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
  mockSetItemAsync.mockResolvedValue(undefined);
  mockDeleteItemAsync.mockResolvedValue(undefined);
});

describe('AuthContext mobile — session restoration', () => {
  it('a. restores session from SecureStore when token is valid', async () => {
    mockGetItemAsync.mockResolvedValue('stored-token');
    mockMe.mockResolvedValue(fakeUser);

    const { result } = renderHook(() => useAuth(), { wrapper });

    // isLoading starts true
    expect(result.current.isLoading).toBe(true);

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockGetItemAsync).toHaveBeenCalledWith(TOKEN_KEY);
    expect(result.current.token).toBe('stored-token');
    expect(result.current.user).toEqual(fakeUser);
  });

  it('b. SecureStore empty → user is null, isLoading becomes false', async () => {
    mockGetItemAsync.mockResolvedValue(null);

    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    // Should not attempt /auth/me when no token stored
    expect(mockMe).not.toHaveBeenCalled();
  });

  it('c. /auth/me returns 401 → token cleared from SecureStore, user is null', async () => {
    mockGetItemAsync.mockResolvedValue('expired-token');
    mockMe.mockRejectedValue(new Error('Unauthorized'));

    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockDeleteItemAsync).toHaveBeenCalledWith(TOKEN_KEY);
    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
  });

  it('d. login calls /auth/me and stores session marker in SecureStore', async () => {
    mockGetItemAsync.mockResolvedValue(null);
    mockLogin.mockResolvedValue({ token_type: 'bearer', expires_in: 1800 });
    mockMe.mockResolvedValue(fakeUser);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.login('doc@example.com', 'password');
    });

    // After cookie-based login, /auth/me is called to get the user profile
    expect(mockMe).toHaveBeenCalled();
    // A session marker is stored in SecureStore
    expect(mockSetItemAsync).toHaveBeenCalledWith(TOKEN_KEY, expect.stringContaining('session:'));
    expect(result.current.user).toEqual(fakeUser);
    expect(result.current.token).toEqual(expect.stringContaining('session:'));
  });

  it('e. logout clears token from SecureStore', async () => {
    mockGetItemAsync.mockResolvedValue('stored-token');
    mockMe.mockResolvedValue(fakeUser);
    mockLogout.mockResolvedValue(undefined);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.logout();
    });

    expect(mockDeleteItemAsync).toHaveBeenCalledWith(TOKEN_KEY);
    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
  });
});

// ─── Property 11 (RBAC) ───────────────────────────────────────────────────────

import * as fc from 'fast-check';

// Feature: role-based-access-control, Property 11: useAuth retourne un UserRole valide
describe('Property 11 — useAuth retourne un UserRole valide (mobile)', () => {
  it('user.role must belong to the valid UserRole union or be null when not authenticated', async () => {
    // Validates: Requirements 7.2
    const VALID_ROLES = ['admin', 'medecin', 'infirmière', 'guest'] as const;

    await fc.assert(
      fc.asyncProperty(
        fc.option(fc.constantFrom(...VALID_ROLES), { nil: null }),
        async (role) => {
          jest.clearAllMocks();
          mockSetItemAsync.mockResolvedValue(undefined);
          mockDeleteItemAsync.mockResolvedValue(undefined);

          if (role !== null) {
            const user = { id: 'u1', email: 'user@example.com', fullName: 'Test User', role };
            mockGetItemAsync.mockResolvedValue('stored-token');
            mockMe.mockResolvedValue(user);
          } else {
            mockGetItemAsync.mockResolvedValue(null);
            mockMe.mockRejectedValue(new Error('Unauthorized'));
          }

          const { result } = renderHook(() => useAuth(), { wrapper });
          await waitFor(() => expect(result.current.isLoading).toBe(false));

          const userRole = result.current.user?.role ?? null;

          // user.role must be null (unauthenticated) or a valid UserRole
          if (userRole !== null) {
            expect(VALID_ROLES).toContain(userRole);
          } else {
            expect(userRole).toBeNull();
          }

          return true;
        },
      ),
      { numRuns: 100 },
    );
  }, 60000);
});
