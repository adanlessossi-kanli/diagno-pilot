/// <reference types="@jest/globals" />
/**
 * Screen-level tests for DiagnoseScreen
 *
 * Feature: testing-coverage
 *
 * Unit tests:
 *  - Symptom submission renders differential diagnoses with probability indicators
 *  - Critical prescription alert renders with testID="alert-critical"
 *
 * Property 15: Critical mobile alerts rendered with correct testID
 *  - For any alert with level = "critical", the rendered element SHALL have testID="alert-critical"
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react-native';
import * as fc from 'fast-check';
import DiagnoseScreen from '../diagnose';

// ─── Mocks ────────────────────────────────────────────────────────────────────

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  useSegments: () => [],
  Link: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock('@expo/vector-icons', () => ({
  Ionicons: () => null,
}));

jest.mock('../../../src/utils/probabilityColor', () => ({
  getProbabilityColor: jest.fn(() => '#22c55e'),
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

const mockDiagnose = jest.fn();
const mockGetPrescription = jest.fn();

jest.mock('../../../src/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'doc@test.com', fullName: 'Dr Test', role: 'medecin' },
    token: 'tok',
    isLoading: false,
    login: jest.fn(),
    logout: jest.fn(),
    apiClient: {
      diagnose: {
        getSymptomsDiagnosis: mockDiagnose,
        getPrescription: mockGetPrescription,
      },
    },
  }),
}));

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const mockDiagnoses = [
  { condition: 'Pneumonie', probability: 0.85, icdCode: 'J18.9', concordantSymptoms: ['fièvre', 'toux'] },
  { condition: 'Bronchite', probability: 0.60, icdCode: 'J20.9', concordantSymptoms: ['toux'] },
  { condition: 'Grippe', probability: 0.45, icdCode: 'J11.1', concordantSymptoms: ['fièvre'] },
];

const mockPrescription = {
  antibiotic: 'Amoxicilline',
  dose_mg: 500,
  frequency: 3,
  duration_days: 7,
  route: 'oral',
};

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
  mockDiagnose.mockResolvedValue({ diagnoses: mockDiagnoses });
  mockGetPrescription.mockResolvedValue({ prescription: mockPrescription, alerts: [] });
});

// ─── Unit tests ───────────────────────────────────────────────────────────────

describe('DiagnoseScreen — symptom submission', () => {
  it('renders differential diagnoses with probability indicators after submission', async () => {
    render(<DiagnoseScreen />);

    // Add a symptom via MobileSymptomInput
    const input = screen.getByPlaceholderText('Nom du symptôme');
    fireEvent.changeText(input, 'fièvre');
    const addButton = screen.getByLabelText('Ajouter le symptôme');
    fireEvent.press(addButton);

    // Submit
    const submitButton = screen.getByText(/obtenir les diagnostics/i);
    await act(async () => {
      fireEvent.press(submitButton);
    });

    await waitFor(() => {
      expect(screen.getByText('Pneumonie')).toBeTruthy();
      expect(screen.getByText('Bronchite')).toBeTruthy();
      expect(screen.getByText('Grippe')).toBeTruthy();
    });

    // Probability indicators (percentages)
    expect(screen.getByText('85%')).toBeTruthy();
    expect(screen.getByText('60%')).toBeTruthy();
    expect(screen.getByText('45%')).toBeTruthy();
  });

  it('calls diagnose API with submitted symptoms', async () => {
    render(<DiagnoseScreen />);

    const input = screen.getByPlaceholderText('Nom du symptôme');
    fireEvent.changeText(input, 'toux');
    const addButton = screen.getByLabelText('Ajouter le symptôme');
    fireEvent.press(addButton);

    const submitButton = screen.getByText(/obtenir les diagnostics/i);
    await act(async () => {
      fireEvent.press(submitButton);
    });

    await waitFor(() => {
      expect(mockDiagnose).toHaveBeenCalledTimes(1);
    });
  });
});

describe('DiagnoseScreen — critical prescription alert', () => {
  it('renders critical alert with testID="alert-critical"', async () => {
    const criticalAlert = {
      level: 'critical' as const,
      type: 'allergy',
      message: 'Allergie connue à la pénicilline',
      affected_drug: 'Amoxicilline',
      alternative: 'Azithromycine',
    };
    mockGetPrescription.mockResolvedValue({
      prescription: mockPrescription,
      alerts: [criticalAlert],
    });

    render(<DiagnoseScreen />);

    // Navigate to prescription step
    const input = screen.getByPlaceholderText('Nom du symptôme');
    fireEvent.changeText(input, 'fièvre');
    const addButton = screen.getByLabelText('Ajouter le symptôme');
    fireEvent.press(addButton);

    const submitButton = screen.getByText(/obtenir les diagnostics/i);
    await act(async () => {
      fireEvent.press(submitButton);
    });

    await waitFor(() => expect(screen.getByText('Pneumonie')).toBeTruthy());

    // Select first diagnosis to get prescription
    await act(async () => {
      fireEvent.press(screen.getByText('Pneumonie'));
    });

    await waitFor(() => {
      expect(screen.getByTestId('alert-critical')).toBeTruthy();
    });
  });

  it('does not render alert-critical testID when no critical alerts', async () => {
    const warningAlert = {
      level: 'warning' as const,
      type: 'interaction',
      message: 'Interaction modérée',
      affected_drug: 'Amoxicilline',
      alternative: null,
    };
    mockGetPrescription.mockResolvedValue({
      prescription: mockPrescription,
      alerts: [warningAlert],
    });

    render(<DiagnoseScreen />);

    const input = screen.getByPlaceholderText('Nom du symptôme');
    fireEvent.changeText(input, 'fièvre');
    const addButton = screen.getByLabelText('Ajouter le symptôme');
    fireEvent.press(addButton);

    const submitButton = screen.getByText(/obtenir les diagnostics/i);
    await act(async () => {
      fireEvent.press(submitButton);
    });

    await waitFor(() => expect(screen.getByText('Pneumonie')).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByText('Pneumonie'));
    });

    await waitFor(() => {
      expect(screen.queryByTestId('alert-critical')).toBeNull();
    });
  });
});

// ─── Property 15: Critical mobile alerts rendered with correct testID ─────────
// Feature: testing-coverage, Property 15: Critical mobile alerts rendered with correct testID

describe('Property 15 — Critical mobile alerts rendered with correct testID', () => {
  it('fc.property: any critical alert renders with testID="alert-critical"', async () => {
    const alertArb = fc.record({
      type: fc.constantFrom('allergy', 'contraindication', 'interaction'),
      message: fc.string({ minLength: 1, maxLength: 80 }),
      affected_drug: fc.string({ minLength: 1, maxLength: 30 }),
      alternative: fc.option(fc.string({ minLength: 1, maxLength: 30 }), { nil: null }),
    });

    await fc.assert(
      fc.asyncProperty(alertArb, async (alertData) => {
        const criticalAlert = { ...alertData, level: 'critical' as const };
        mockGetPrescription.mockResolvedValue({
          prescription: mockPrescription,
          alerts: [criticalAlert],
        });
        mockDiagnose.mockResolvedValue({ diagnoses: mockDiagnoses });

        const { unmount } = render(<DiagnoseScreen />);

        const input = screen.getByPlaceholderText('Nom du symptôme');
        fireEvent.changeText(input, 'fièvre');
        const addButton = screen.getByLabelText('Ajouter le symptôme');
        fireEvent.press(addButton);

        const submitButton = screen.getByText(/obtenir les diagnostics/i);
        await act(async () => {
          fireEvent.press(submitButton);
        });

        await waitFor(() => expect(screen.getByText('Pneumonie')).toBeTruthy());

        await act(async () => {
          fireEvent.press(screen.getByText('Pneumonie'));
        });

        await waitFor(() => {
          expect(screen.getByTestId('alert-critical')).toBeTruthy();
        });

        unmount();
      }),
      { numRuns: 100 }
    );
  }, 120000);
});
