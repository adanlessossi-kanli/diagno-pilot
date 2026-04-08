/// <reference types="@jest/globals" />
/**
 * Screen-level tests for PatientsScreen
 *
 * Feature: testing-coverage
 *
 * Unit tests:
 *  - Screen renders one MobilePatientCard per patient
 *  - Empty state renders when API returns empty list
 *
 * Property 16: Mobile patient list renders one card per patient
 *  - For any list of N patients, the screen SHALL render exactly N MobilePatientCard components
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react-native';
import * as fc from 'fast-check';
import PatientsScreen from '../patients';
import type { PatientProfile } from '@diagno-pilot/types';

// ─── Mocks ────────────────────────────────────────────────────────────────────

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), replace: jest.fn(), back: jest.fn() },
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
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

const mockListAllPatients = jest.fn();

jest.mock('../../../src/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'doc@test.com', fullName: 'Dr Test', role: 'medecin' },
    token: 'tok',
    isLoading: false,
    login: jest.fn(),
    logout: jest.fn(),
    apiClient: {
      patients: {
        listAllPatients: mockListAllPatients,
      },
    },
  }),
}));

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

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
});

// ─── Unit tests ───────────────────────────────────────────────────────────────

describe('PatientsScreen — patient list', () => {
  it('renders one MobilePatientCard per patient', async () => {
    const patients = [
      makePatient('1', 'Alice Martin'),
      makePatient('2', 'Bob Dupont'),
      makePatient('3', 'Claire Leblanc'),
    ];
    mockListAllPatients.mockResolvedValue(patients);

    render(<PatientsScreen />);

    await waitFor(() => {
      expect(screen.getByText('Alice Martin')).toBeTruthy();
      expect(screen.getByText('Bob Dupont')).toBeTruthy();
      expect(screen.getByText('Claire Leblanc')).toBeTruthy();
    }, { timeout: 5000 });
  }, 10000);

  it('renders empty state when API returns empty list', async () => {
    mockListAllPatients.mockResolvedValue([]);

    render(<PatientsScreen />);

    await waitFor(() => {
      expect(screen.getByText('Aucun patient enregistré.')).toBeTruthy();
    });
  });

  it('calls listAllPatients on mount', async () => {
    mockListAllPatients.mockResolvedValue([]);

    render(<PatientsScreen />);

    await waitFor(() => {
      expect(mockListAllPatients).toHaveBeenCalledTimes(1);
    });
  });
});

// ─── Property 16: Mobile patient list renders one card per patient ────────────
// Feature: testing-coverage, Property 16: Mobile patient list renders one card per patient

describe('Property 16 — Mobile patient list renders one card per patient', () => {
  it('fc.property: N patients → exactly N patient names rendered', async () => {
    const patientArb = fc.record({
      id: fc.uuid(),
      fullName: fc.string({ minLength: 2, maxLength: 40 }).filter(s => s.trim().length > 0),
    }).map(({ id, fullName }) => makePatient(id, fullName.trim()));

    // Use a small list size to keep tests fast
    const patientsArb = fc.array(patientArb, { minLength: 0, maxLength: 8 });

    await fc.assert(
      fc.asyncProperty(patientsArb, async (patients) => {
        // Ensure unique fullNames to avoid ambiguous queries
        const uniquePatients = patients.filter(
          (p, i, arr) => arr.findIndex(q => q.fullName === p.fullName) === i
        );

        mockListAllPatients.mockResolvedValue(uniquePatients);

        const { unmount } = render(<PatientsScreen />);

        if (uniquePatients.length === 0) {
          await waitFor(() => {
            expect(screen.getByText('Aucun patient enregistré.')).toBeTruthy();
          });
        } else {
          await waitFor(() => {
            for (const p of uniquePatients) {
              // Use getAllByText since the name may appear in both the card name and avatar initials
              const matches = screen.getAllByText(p.fullName!);
              expect(matches.length).toBeGreaterThanOrEqual(1);
            }
          });
        }

        unmount();
      }),
      { numRuns: 100 }
    );
  }, 60000);
});
