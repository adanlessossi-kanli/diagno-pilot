/// <reference types="@jest/globals" />
/**
 * Screen-level tests for PatientDetailScreen
 *
 * Feature: testing-coverage
 *
 * Unit tests:
 *  - Patient name, weight, and allergy list are rendered
 *
 * Property 17: Mobile patient detail renders required fields
 *  - For any patient with non-null full_name, weight_kg, allergies,
 *    the rendered screen SHALL display each field
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react-native';
import * as fc from 'fast-check';
import PatientDetailScreen from '../[id]';
import type { PatientProfile } from '@diagno-pilot/types';

// ─── Mocks ────────────────────────────────────────────────────────────────────

jest.mock('expo-router', () => ({
  useLocalSearchParams: jest.fn(() => ({ id: 'patient-1' })),
  router: { push: jest.fn(), replace: jest.fn(), back: jest.fn() },
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  useSegments: () => [],
  Link: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock('@diagno-pilot/ui/src/tokens', () => ({
  colors: {
    primary: { 600: '#2563eb' },
    neutral: { 200: '#e5e7eb', 400: '#9ca3af', 500: '#6b7280', 900: '#111827' },
    error: { bg: '#fef2f2', border: '#fca5a5', text: '#dc2626' },
    warning: { bg: '#fffbeb', border: '#fcd34d', text: '#d97706' },
    info: { bg: '#eff6ff', border: '#93c5fd', text: '#1d4ed8' },
  },
  spacing: { 2: 8, 3: 12, 4: 16 },
  radius: { sm: 4, lg: 10, full: 9999 },
  typography: { xs: 11, sm: 13, base: 15, lg: 18 },
  shadow: { mobile: { sm: 2 } },
}));

// ─── Mock AuthContext ─────────────────────────────────────────────────────────

const mockGetPatient = jest.fn();
const mockListConsultations = jest.fn();

jest.mock('../../../src/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'doc@test.com', fullName: 'Dr Test', role: 'medecin' },
    token: 'tok',
    isLoading: false,
    login: jest.fn(),
    logout: jest.fn(),
    apiClient: {
      patients: {
        getPatient: mockGetPatient,
        listConsultations: mockListConsultations,
      },
    },
  }),
}));

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makePatient(overrides: Partial<PatientProfile> = {}): PatientProfile {
  return {
    id: 'patient-1',
    fullName: 'Alice Martin',
    ageGroup: 'adult',
    weightKg: 65,
    dateOfBirth: '1985-03-15',
    allergies: ['Pénicilline', 'Aspirine'],
    renalFailure: false,
    hepaticFailure: false,
    currentMedications: [],
    ...overrides,
  };
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
  mockListConsultations.mockResolvedValue([]);
});

// ─── Unit tests ───────────────────────────────────────────────────────────────

describe('PatientDetailScreen — required fields', () => {
  it('renders patient full name', async () => {
    mockGetPatient.mockResolvedValue(makePatient({ fullName: 'Alice Martin' }));

    render(<PatientDetailScreen />);

    await waitFor(() => {
      expect(screen.getByText('Alice Martin')).toBeTruthy();
    });
  });

  it('renders patient weight', async () => {
    mockGetPatient.mockResolvedValue(makePatient({ weightKg: 65 }));

    render(<PatientDetailScreen />);

    await waitFor(() => {
      expect(screen.getByText('65 kg')).toBeTruthy();
    });
  });

  it('renders allergy count when patient has allergies', async () => {
    mockGetPatient.mockResolvedValue(makePatient({ allergies: ['Pénicilline', 'Aspirine'] }));

    render(<PatientDetailScreen />);

    await waitFor(() => {
      // MobilePatientCard renders "2 connue(s)" for 2 allergies
      expect(screen.getByText('2 connue(s)')).toBeTruthy();
    });
  });

  it('renders "Aucune" when patient has no allergies', async () => {
    mockGetPatient.mockResolvedValue(makePatient({ allergies: [] }));

    render(<PatientDetailScreen />);

    await waitFor(() => {
      expect(screen.getByText('Aucune')).toBeTruthy();
    });
  });

  it('renders "Patient introuvable" when API returns null', async () => {
    mockGetPatient.mockResolvedValue(null);

    render(<PatientDetailScreen />);

    await waitFor(() => {
      expect(screen.getByText('Patient introuvable.')).toBeTruthy();
    });
  });
});

// ─── Property 17: Mobile patient detail renders required fields ───────────────
// Feature: testing-coverage, Property 17: Mobile patient detail renders required fields

describe('Property 17 — Mobile patient detail renders required fields', () => {
  it('fc.property: any patient with non-null full_name, weight_kg, allergies → all displayed', async () => {
    const patientArb = fc.record({
      fullName: fc.string({ minLength: 2, maxLength: 40 }).filter(s => s.trim().length > 0),
      weightKg: fc.float({ min: 1, max: 200, noNaN: true }),
      allergies: fc.array(
        fc.string({ minLength: 1, maxLength: 20 }).filter(s => s.trim().length > 0),
        { minLength: 0, maxLength: 5 }
      ),
    });

    await fc.assert(
      fc.asyncProperty(patientArb, async ({ fullName, weightKg, allergies }) => {
        const trimmedName = fullName.trim();
        const roundedWeight = Math.round(weightKg * 10) / 10;
        const patient = makePatient({
          fullName: trimmedName,
          weightKg: roundedWeight,
          allergies,
        });

        mockGetPatient.mockResolvedValue(patient);
        mockListConsultations.mockResolvedValue([]);

        const { unmount } = render(<PatientDetailScreen />);

        await waitFor(() => {
          // Full name is displayed
          expect(screen.getByText(trimmedName)).toBeTruthy();

          // Weight is displayed
          expect(screen.getByText(`${roundedWeight} kg`)).toBeTruthy();

          // Allergies count or "Aucune" is displayed
          if (allergies.length > 0) {
            expect(screen.getByText(`${allergies.length} connue(s)`)).toBeTruthy();
          } else {
            expect(screen.getByText('Aucune')).toBeTruthy();
          }
        });

        unmount();
      }),
      { numRuns: 100 }
    );
  }, 60000);
});
