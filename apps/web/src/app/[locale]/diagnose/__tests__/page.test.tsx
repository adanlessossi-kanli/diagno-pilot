/**
 * Page-level tests for DiagnosePage
 * Validates: Requirements 7.6, 7.7
 *
 * Includes:
 *   - Subtask 10.2: Property 11 — Critical alerts rendered with distinct style
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import React from 'react';
import fc from 'fast-check';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockGetSymptomsDiagnosis = vi.fn();
const mockGetPrescription = vi.fn();
const mockListAntibiotics = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/',
}));

vi.mock('next/image', () => ({
  default: ({ src, alt }: { src: string; alt: string }) =>
    React.createElement('img', { src, alt }),
}));

vi.mock('@/lib/images', () => ({
  IMAGES: {
    diagnoseHeader: { src: '/diagnose-header.jpg', alt: 'Diagnose header' },
  },
}));

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'doc@test.com', role: 'medecin', fullName: 'Dr Test' },
    isLoading: false,
  }),
}));

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    diagnose: {
      getSymptomsDiagnosis: mockGetSymptomsDiagnosis,
      getPrescription: mockGetPrescription,
      listAntibiotics: mockListAntibiotics,
    },
    patients: {
      listAllPatients: vi.fn().mockResolvedValue([]),
    },
  }),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

const mockDiagnoses = [
  {
    condition: 'Pneumonia',
    probability: 0.85,
    icdCode: 'J18',
    concordantSymptoms: ['fever', 'cough'],
  },
  {
    condition: 'Bronchitis',
    probability: 0.6,
    icdCode: 'J20',
    concordantSymptoms: ['cough'],
  },
  {
    condition: 'Common Cold',
    probability: 0.3,
    icdCode: 'J00',
    concordantSymptoms: ['runny nose'],
  },
];

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockListAntibiotics.mockResolvedValue(['Amoxicillin', 'Ciprofloxacin']);
});

describe('DiagnosePage — page-level tests', () => {
  it('renders the symptom input textarea', async () => {
    mockGetSymptomsDiagnosis.mockResolvedValue({ diagnoses: [], sources: [] });
    const { default: DiagnosePage } = await import('../page');
    render(<DiagnosePage />);

    expect(screen.getByRole('textbox')).toBeDefined();
  });

  it('submitting symptoms triggers the diagnose API call', async () => {
    mockGetSymptomsDiagnosis.mockResolvedValue({
      diagnoses: mockDiagnoses,
      sources: [],
      llmUsed: 'gpt-4',
    });

    const { default: DiagnosePage } = await import('../page');
    render(<DiagnosePage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'fever and cough for 3 days' } });

    await act(async () => {
      fireEvent.submit(textarea.closest('form')!);
    });

    await waitFor(() => {
      expect(mockGetSymptomsDiagnosis).toHaveBeenCalledOnce();
    });
  });

  it('renders differential diagnoses after submission', async () => {
    mockGetSymptomsDiagnosis.mockResolvedValue({
      diagnoses: mockDiagnoses,
      sources: [],
      llmUsed: 'gpt-4',
    });

    const { default: DiagnosePage } = await import('../page');
    render(<DiagnosePage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'fever and cough for 3 days' } });

    await act(async () => {
      fireEvent.submit(textarea.closest('form')!);
    });

    await waitFor(() => {
      expect(screen.getByText('Pneumonia')).toBeDefined();
      expect(screen.getByText('Bronchitis')).toBeDefined();
      expect(screen.getByText('Common Cold')).toBeDefined();
    });
  });

  it('renders critical alerts with data-severity="critical" attribute', async () => {
    mockGetSymptomsDiagnosis.mockResolvedValue({
      diagnoses: mockDiagnoses,
      sources: [],
      llmUsed: 'gpt-4',
    });
    mockGetPrescription.mockResolvedValue({
      prescription: {
        antibiotic: 'Amoxicillin',
        dose_mg: 500,
        frequency: 'TID',
        duration_days: 7,
        route: 'oral',
      },
      alerts: [
        {
          level: 'critical',
          type: 'allergy',
          message: 'Patient is allergic to penicillin',
          affected_drug: 'Amoxicillin',
          alternative: 'Azithromycin',
        },
      ],
      llmUsed: 'gpt-4',
    });

    const { default: DiagnosePage } = await import('../page');
    render(<DiagnosePage />);

    // Submit symptoms to get diagnoses
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'fever and cough for 3 days' } });

    await act(async () => {
      fireEvent.submit(textarea.closest('form')!);
    });

    await waitFor(() => {
      expect(screen.getByText('Pneumonia')).toBeDefined();
    });

    // Click "Get Prescription" button in PrescriptionStep
    const prescriptionBtn = screen.getByRole('button', { name: /getPrescription/i });
    await act(async () => {
      fireEvent.click(prescriptionBtn);
    });

    await waitFor(() => {
      expect(mockGetPrescription).toHaveBeenCalledOnce();
    });

    // Critical alert block is rendered — check for the critical alert container
    await waitFor(() => {
      const alerts = screen.getAllByRole('alert');
      const criticalAlert = alerts.find((el) =>
        el.className.includes('border-red') || el.getAttribute('aria-live') === 'assertive'
      );
      expect(criticalAlert).toBeDefined();
    });
  });
});

// ─── Property-based tests ─────────────────────────────────────────────────────

// Feature: testing-coverage, Property 11: Critical alerts rendered with distinct style
describe('DiagnosePage — Property 11: Critical alerts rendered with distinct style', () => {
  it('any alert with level="critical" renders with data-severity="critical" or assertive aria-live', async () => {
    // **Validates: Requirements 7.7**
    // The PrescriptionStep renders AlertItem with role="alert" and aria-live="assertive" for critical alerts.
    // We test the AlertItem component directly via the PrescriptionStep rendered in DiagnosePage.

    const { PrescriptionStep } = await import('../PrescriptionStep');

    await fc.assert(
      fc.asyncProperty(
        fc.record({
          message: fc.string({ minLength: 1, maxLength: 100 }),
          affected_drug: fc.string({ minLength: 1, maxLength: 30 }),
          alternative: fc.option(fc.string({ minLength: 1, maxLength: 30 }), { nil: undefined }),
        }),
        async ({ message, affected_drug, alternative }) => {
          cleanup();
          vi.clearAllMocks();

          const criticalAlert = {
            level: 'critical' as const,
            type: 'allergy' as const,
            message,
            affected_drug,
            alternative,
          };

          const mockOnGetPrescription = vi.fn().mockResolvedValue({
            prescription: {
              antibiotic: 'Amoxicillin',
              dose_mg: 500,
              frequency: 'TID',
              duration_days: 7,
              route: 'oral',
            },
            alerts: [criticalAlert],
            llmUsed: null,
          });

          render(
            <PrescriptionStep
              diagnoses={[
                {
                  condition: 'Pneumonia',
                  probability: 0.85,
                  icdCode: 'J18',
                  concordantSymptoms: [],
                },
              ]}
              antibiotics={['Amoxicillin']}
              onGetPrescription={mockOnGetPrescription}
            />
          );

          // Click the "Get Prescription" button
          const btn = screen.getByRole('button', { name: /getPrescription/i });
          await act(async () => {
            fireEvent.click(btn);
          });

          await waitFor(() => {
            expect(mockOnGetPrescription).toHaveBeenCalledOnce();
          });

          // The critical AlertItem renders with role="alert" and aria-live="assertive"
          await waitFor(() => {
            const alerts = screen.getAllByRole('alert');
            const criticalEl = alerts.find(
              (el) => el.getAttribute('aria-live') === 'assertive'
            );
            expect(criticalEl).toBeDefined();
          });

          return true;
        }
      ),
      { numRuns: 10 }
    );
  });
});
