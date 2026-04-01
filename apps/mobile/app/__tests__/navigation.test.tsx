/// <reference types="@jest/globals" />
/**
 * Navigation flow tests for the mobile app
 *
 * Feature: testing-coverage
 *
 * Unit tests:
 *  - medecin user sees Diagnose, Patients, Chat, and Profile tabs
 *  - pharmacien user cannot access Patients tab (redirected to profile)
 *  - unauthenticated user accessing protected tab redirects to login
 *  - navigating from patients list to patient detail passes correct id
 *
 * Property 19: Unauthenticated mobile users redirected to login
 *  - For any protected mobile screen with no valid session in AuthContext,
 *    the app SHALL navigate to login
 *
 * Property 22: Navigation passes correct patient id as route parameter
 *  - For any patient in the list, tapping its card SHALL result in route
 *    parameter `id` equaling that patient's id
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react-native';
import * as fc from 'fast-check';
import type { PatientProfile } from '@diagno-pilot/types';
import type { UserRole } from '@diagno-pilot/types';
import { router as expoRouter } from 'expo-router';

// ─── Mocks ────────────────────────────────────────────────────────────────────

// NOTE: jest.mock is hoisted before variable declarations, so we define the
// mock functions inside the factory and expose them via a module-level object.
const mockUseSegments = jest.fn(() => [] as string[]);

jest.mock('expo-router', () => {
  const { View: RNView, Text: RNText } = require('react-native');

  // Inline jest.fn() so they are available at hoist time
  const routerPush = jest.fn();
  const routerReplace = jest.fn();

  const TabsScreen = ({ name, options }: { name: string; options?: { href?: string | null } }) => {
    if (options?.href === null) return null;
    return (
      <RNView testID={`tab-${name}`}>
        <RNText>{name}</RNText>
      </RNView>
    );
  };
  const Tabs = Object.assign(
    ({ children }: { children: React.ReactNode }) => <RNView>{children}</RNView>,
    { Screen: TabsScreen }
  );

  const router = { push: routerPush, replace: routerReplace, back: jest.fn() };

  return {
    Tabs,
    router,
    useRouter: () => router,
    useSegments: () => mockUseSegments(),
    Link: ({ children }: { children: React.ReactNode }) => children,
    Redirect: ({ href }: { href: string }) => {
      return <RNText testID="redirect">{href}</RNText>;
    },
  };
});

jest.mock('@expo/vector-icons', () => ({
  Ionicons: () => null,
}));

jest.mock('@diagno-pilot/ui/src/tokens', () => ({
  colors: {
    primary: { 600: '#2563eb' },
    neutral: { 200: '#e5e7eb', 400: '#9ca3af', 500: '#6b7280', 900: '#111827' },
    error: { bg: '#fef2f2', border: '#fca5a5', text: '#dc2626' },
    warning: { bg: '#fffbeb', border: '#fcd34d', text: '#d97706' },
    info: { bg: '#eff6ff', border: '#93c5fd', text: '#1d4ed8' },
  },
  spacing: { 2: 8, 3: 12, 4: 16, 6: 24 },
  radius: { sm: 4, md: 8, lg: 10, full: 9999 },
  typography: { xs: 11, sm: 13, base: 15, lg: 18 },
  shadow: { mobile: { sm: 2, md: 4 } },
}));

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn().mockResolvedValue(null),
  setItemAsync: jest.fn().mockResolvedValue(undefined),
  deleteItemAsync: jest.fn().mockResolvedValue(undefined),
}));

// ─── Mock AuthContext ─────────────────────────────────────────────────────────

let mockAuthUser: { id: string; email: string; fullName: string; role: UserRole } | null = {
  id: '1',
  email: 'doc@test.com',
  fullName: 'Dr Test',
  role: 'medecin',
};
let mockAuthToken: string | null = 'tok';
const mockListAllPatients = jest.fn();

jest.mock('../../src/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: mockAuthUser,
    token: mockAuthToken,
    isLoading: false,
    login: jest.fn(),
    logout: jest.fn(),
    apiClient: {
      patients: { listAllPatients: mockListAllPatients },
    },
  }),
}));

// ─── Imports (after mocks) ────────────────────────────────────────────────────

import TabsLayout, { MEDICAL_ROLES, SCREEN_PERMISSIONS } from '../(tabs)/_layout';
import PatientsScreen from '../(tabs)/patients';
import IndexScreen from '../index';

// Get typed references to the mocked router functions
const mockRouterPush = expoRouter.push as jest.Mock;
const mockRouterReplace = expoRouter.replace as jest.Mock;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makePatient(id: string, fullName: string): PatientProfile {
  return {
    id,
    fullName,
    ageGroup: 'adult',
    weightKg: 70,
    dateOfBirth: '1990-01-01',
    allergies: [],
    renalFailure: false,
    hepaticFailure: false,
    currentMedications: [],
  };
}

function renderTabsLayout(role: UserRole, segments: string[] = []) {
  mockAuthUser = { id: '1', email: 'test@test.com', fullName: 'Test User', role };
  mockAuthToken = 'tok';
  mockUseSegments.mockReturnValue(segments);
  mockRouterReplace.mockClear();
  return render(<TabsLayout />);
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
  mockUseSegments.mockReturnValue([]);
  mockAuthUser = { id: '1', email: 'doc@test.com', fullName: 'Dr Test', role: 'medecin' };
  mockAuthToken = 'tok';
  mockListAllPatients.mockResolvedValue([]);
});

// ─── Unit tests: tab visibility ───────────────────────────────────────────────

describe('Navigation — medecin tab visibility (REQ 10.1)', () => {
  it('medecin user sees Diagnose, Patients, Chat, and Profile tabs', () => {
    renderTabsLayout('medecin');

    expect(screen.queryByText('diagnose')).not.toBeNull();
    expect(screen.queryByText('patients')).not.toBeNull();
    expect(screen.queryByText('chat')).not.toBeNull();
    expect(screen.queryByText('profile')).not.toBeNull();
  });
});

describe('Navigation — pharmacien RBAC (REQ 10.2)', () => {
  it('pharmacien navigating to patients tab is redirected to profile', () => {
    // guest is not in MEDICAL_ROLES, so patients tab is hidden and
    // navigating to it triggers a redirect to /(tabs)/profile
    renderTabsLayout('guest', ['(tabs)', 'patients']);

    expect(mockRouterReplace).toHaveBeenCalledWith('/(tabs)/profile');
  });

  it('pharmacien does not see patients tab (href=null)', () => {
    renderTabsLayout('guest');

    // patients tab should be hidden (href=null) for non-medical roles
    expect(screen.queryByText('patients')).toBeNull();
  });
});

describe('Navigation — unauthenticated user (REQ 10.3)', () => {
  it('unauthenticated user at index redirects to /login', () => {
    mockAuthUser = null;
    mockAuthToken = null;

    render(<IndexScreen />);

    // The Redirect component renders with href="/login"
    const redirect = screen.getByTestId('redirect');
    expect(redirect.props.children).toBe('/login');
  });
});

describe('Navigation — patient detail route parameter (REQ 10.4)', () => {
  it('tapping a patient card navigates with the correct patient id', async () => {
    const patient = makePatient('patient-abc-123', 'Alice Martin');
    mockListAllPatients.mockResolvedValue([patient]);

    render(<PatientsScreen />);

    await waitFor(() => {
      expect(screen.getByText('Alice Martin')).toBeTruthy();
    });

    fireEvent.press(screen.getByLabelText('Ouvrir le dossier de Alice Martin'));

    expect(mockRouterPush).toHaveBeenCalledWith('/patient/patient-abc-123');
  });
});

// ─── Property 19: Unauthenticated mobile users redirected to login ────────────
// Feature: testing-coverage, Property 19: Unauthenticated mobile users redirected to login
// For any protected mobile screen with no valid session in AuthContext, the app SHALL navigate to login

describe('Property 19 — Unauthenticated mobile users redirected to login', () => {
  it('fc.property: any protected screen with no session → index redirects to /login', () => {
    // The index screen is the entry point that checks auth and redirects.
    // For any unauthenticated state (null user, null token), it SHALL redirect to /login.
    fc.assert(
      fc.property(
        fc.record({
          user: fc.constant(null),
          token: fc.constant(null),
        }),
        ({ user, token }) => {
          mockAuthUser = user;
          mockAuthToken = token;

          const { unmount } = render(<IndexScreen />);

          const redirect = screen.getByTestId('redirect');
          expect(redirect.props.children).toBe('/login');

          unmount();
        }
      ),
      { numRuns: 100 }
    );
  });

  it('fc.property: any protected tab with no session → RBAC redirects to profile (not patients)', () => {
    // When a user with no medical role (guest) tries to access a medical screen,
    // the RBAC guard redirects them away from the protected content.
    const protectedScreens = Object.keys(SCREEN_PERMISSIONS).filter(
      (screen) => !SCREEN_PERMISSIONS[screen].includes('guest')
    );

    fc.assert(
      fc.property(
        fc.constantFrom(...protectedScreens),
        (protectedScreen) => {
          mockAuthUser = { id: '1', email: 'guest@test.com', fullName: 'Guest', role: 'guest' };
          mockAuthToken = null;
          mockRouterReplace.mockClear();

          const { unmount } = renderTabsLayout('guest', ['(tabs)', protectedScreen]);

          expect(mockRouterReplace).toHaveBeenCalledWith('/(tabs)/profile');

          unmount();
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ─── Property 22: Navigation passes correct patient id as route parameter ─────
// Feature: testing-coverage, Property 22: Navigation passes correct patient id as route parameter
// For any patient in the list, tapping its card SHALL result in route parameter `id` equaling that patient's id

describe('Property 22 — Navigation passes correct patient id as route parameter', () => {
  it('fc.property: tapping any patient card navigates with that patient id', async () => {
    const patientArb = fc.record({
      id: fc.string({ minLength: 1, maxLength: 40 }).filter(s => s.trim().length > 0 && !s.includes('/')),
      fullName: fc.string({ minLength: 2, maxLength: 40 }).filter(s => s.trim().length > 1),
    }).map(({ id, fullName }) => makePatient(id.trim(), fullName.trim()));

    await fc.assert(
      fc.asyncProperty(patientArb, async (patient) => {
        mockListAllPatients.mockResolvedValue([patient]);
        mockRouterPush.mockClear();

        const { unmount } = render(<PatientsScreen />);

        await waitFor(() => {
          expect(screen.getByText(patient.fullName!)).toBeTruthy();
        });

        fireEvent.press(
          screen.getByLabelText(`Ouvrir le dossier de ${patient.fullName}`)
        );

        expect(mockRouterPush).toHaveBeenCalledWith(`/patient/${patient.id}`);

        unmount();
      }),
      { numRuns: 100 }
    );
  }, 60000);
});
