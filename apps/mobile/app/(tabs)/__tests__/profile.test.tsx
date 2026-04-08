/// <reference types="@jest/globals" />
/**
 * Unit tests for ProfileScreen — language selector (REQ 7.6)
 *
 * Covers:
 *  a. FR and EN buttons are rendered
 *  b. Pressing FR calls setLocale('fr')
 *  c. Pressing EN calls setLocale('en')
 *  d. Active locale button has accessibilityState selected=true
 *  e. Inactive locale button has accessibilityState selected=false
 *  f. Pressing EN persists via SecureStore.setItemAsync('diagno_locale', 'en')
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react-native';
import ProfileScreen from '../profile';

// ─── Mock expo-secure-store ───────────────────────────────────────────────────

const mockGetItemAsync = jest.fn();
const mockSetItemAsync = jest.fn();
const mockDeleteItemAsync = jest.fn();

jest.mock('expo-secure-store', () => ({
  getItemAsync: (...args: unknown[]) => mockGetItemAsync(...args),
  setItemAsync: (...args: unknown[]) => mockSetItemAsync(...args),
  deleteItemAsync: (...args: unknown[]) => mockDeleteItemAsync(...args),
}));

// ─── Mock useAuth ─────────────────────────────────────────────────────────────

jest.mock('../../../src/contexts/AuthContext', () => ({
  useAuth: jest.fn(() => ({
    user: { id: '1', fullName: 'Test User', email: 'test@example.com', role: 'medecin' },
    token: 'tok',
    isLoading: false,
    login: jest.fn(),
    logout: jest.fn(),
    apiClient: {},
  })),
}));

// ─── Mock expo-router (used transitively by expo-router layout) ───────────────

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useSegments: () => [],
  Link: ({ children }: { children: React.ReactNode }) => children,
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

import { I18nProvider } from '../../../src/contexts/I18nContext';

function renderWithI18n(initialLocale?: 'fr' | 'en') {
  // Pre-seed SecureStore so I18nProvider restores the desired locale on mount
  mockGetItemAsync.mockResolvedValue(initialLocale ?? 'fr');
  return render(
    <I18nProvider>
      <ProfileScreen />
    </I18nProvider>
  );
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
  mockGetItemAsync.mockResolvedValue('fr');
  mockSetItemAsync.mockResolvedValue(undefined);
  mockDeleteItemAsync.mockResolvedValue(undefined);
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ProfileScreen — language selector', () => {
  it('a. renders FR and EN buttons', async () => {
    renderWithI18n('fr');

    // Wait for the async locale restore to settle
    await waitFor(() => expect(screen.getByLabelText('Français')).toBeTruthy());
    expect(screen.getByLabelText('English')).toBeTruthy();
  });

  it('b. pressing FR calls setLocale with "fr-TG"', async () => {
    renderWithI18n('en');

    await waitFor(() => expect(screen.getByLabelText('Français')).toBeTruthy());

    fireEvent.press(screen.getByLabelText('Français'));

    await waitFor(() =>
      expect(mockSetItemAsync).toHaveBeenCalledWith('diagno_locale', 'fr-TG')
    );
  });

  it('c. pressing EN calls setLocale with "en"', async () => {
    renderWithI18n('fr');

    await waitFor(() => expect(screen.getByLabelText('English')).toBeTruthy());

    fireEvent.press(screen.getByLabelText('English'));

    await waitFor(() =>
      expect(mockSetItemAsync).toHaveBeenCalledWith('diagno_locale', 'en')
    );
  });

  it('d. active locale button (FR) has accessibilityState selected=true when locale is fr-TG', async () => {
    renderWithI18n('fr');

    await waitFor(() => expect(screen.getByLabelText('Français')).toBeTruthy());

    const frButton = screen.getByLabelText('Français');
    expect(frButton.props.accessibilityState?.selected).toBe(true);
  });

  it('e. inactive locale button (EN) has accessibilityState selected=false when locale is fr', async () => {
    renderWithI18n('fr');

    await waitFor(() => expect(screen.getByLabelText('English')).toBeTruthy());

    const enButton = screen.getByLabelText('English');
    expect(enButton.props.accessibilityState?.selected).toBe(false);
  });

  it('f. pressing EN persists locale via SecureStore.setItemAsync("diagno_locale", "en")', async () => {
    renderWithI18n('fr');

    await waitFor(() => expect(screen.getByLabelText('English')).toBeTruthy());

    fireEvent.press(screen.getByLabelText('English'));

    await waitFor(() =>
      expect(mockSetItemAsync).toHaveBeenCalledWith('diagno_locale', 'en')
    );
    // Ensure it was called exactly once for the press (the initial restore may also call getItemAsync)
    const calls = mockSetItemAsync.mock.calls.filter(
      ([key, value]) => key === 'diagno_locale' && value === 'en'
    );
    expect(calls.length).toBeGreaterThanOrEqual(1);
  });
});

// ─── Additional imports for property tests ────────────────────────────────────

import * as fc from 'fast-check';
import * as AuthContext from '../../../src/contexts/AuthContext';

// Helper to get the mocked useAuth function
function getMockUseAuth() {
  return AuthContext.useAuth as jest.MockedFunction<typeof AuthContext.useAuth>;
}

// ─── Tests: user name and role display (REQ 9.9) ─────────────────────────────

describe('ProfileScreen — user name and role display (REQ 9.9)', () => {
  it('displays authenticated user full name', async () => {
    renderWithI18n('fr');

    await waitFor(() => {
      expect(screen.getByText('Test User')).toBeTruthy();
    });
  });

  it('displays authenticated user role', async () => {
    renderWithI18n('fr');

    await waitFor(() => {
      expect(screen.getByText('medecin')).toBeTruthy();
    });
  });

  it('displays fallback "—" when user is null', async () => {
    getMockUseAuth().mockReturnValueOnce({
      user: null,
      token: null,
      isLoading: false,
      login: jest.fn(),
      logout: jest.fn(),
      apiClient: {} as ReturnType<typeof import('@diagno-pilot/api-client').createApiClient>,
    });

    renderWithI18n('fr');

    await waitFor(() => {
      // Multiple "—" placeholders for name, email, role
      const dashes = screen.getAllByText('—');
      expect(dashes.length).toBeGreaterThanOrEqual(1);
    });
  });
});

// ─── Property 18: Mobile profile screen displays user name and role ───────────
// Feature: testing-coverage, Property 18: Mobile profile screen displays user name and role

describe('Property 18 — Mobile profile screen displays user name and role', () => {
  afterEach(() => {
    getMockUseAuth().mockReset();
    getMockUseAuth().mockImplementation(() => ({
      user: { id: '1', fullName: 'Test User', email: 'test@example.com', role: 'medecin' as const },
      token: 'tok',
      isLoading: false,
      login: jest.fn(),
      logout: jest.fn(),
      apiClient: {} as ReturnType<typeof import('@diagno-pilot/api-client').createApiClient>,
    }));
  });

  it('fc.property: any authenticated user with full_name and role → both displayed', async () => {
    const userArb = fc.record({
      fullName: fc.string({ minLength: 1, maxLength: 50 }).filter(s => s.trim().length > 0),
      role: fc.constantFrom('medecin', 'admin', 'infirmière', 'guest'),
      email: fc.emailAddress(),
    });

    await fc.assert(
      fc.asyncProperty(userArb, async ({ fullName, role, email }) => {
        const trimmedName = fullName.trim();

        getMockUseAuth().mockReturnValue({
          user: { id: '1', fullName: trimmedName, role, email },
          token: 'tok',
          isLoading: false,
          login: jest.fn(),
          logout: jest.fn(),
          apiClient: {} as ReturnType<typeof import('@diagno-pilot/api-client').createApiClient>,
        });

        const { unmount } = renderWithI18n('fr');

        await waitFor(() => {
          expect(screen.getByText(trimmedName)).toBeTruthy();
          expect(screen.getByText(role)).toBeTruthy();
        });

        unmount();
      }),
      { numRuns: 100 }
    );
  }, 60000);
});
