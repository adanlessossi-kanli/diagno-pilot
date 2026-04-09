/**
 * Preservation property tests — Unchanged Diagnose Behaviors
 *
 * These tests capture baseline behavior that MUST PASS on the current unfixed code.
 * After the fix is applied, these tests verify no regressions were introduced.
 *
 * **Validates: Requirements 3.3**
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import React from 'react';
import fc from 'fast-check';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockGetSymptomsDiagnosis = vi.fn();
const mockListAntibiotics = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'fr',
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
    user: { id: 'u1', email: 'doc@test.com', role: 'medecin', fullName: 'Dr Test' },
    isLoading: false,
  }),
}));

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    diagnose: {
      getSymptomsDiagnosis: mockGetSymptomsDiagnosis,
      listAntibiotics: mockListAntibiotics,
      getPrescription: vi.fn(),
      getSession: vi.fn(),
      listMyConsultations: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 }),
    },
    patients: {
      listAllPatients: vi.fn().mockResolvedValue([]),
    },
    chat: {
      sendMessageStream: vi.fn(),
    },
  }),
}));

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockListAntibiotics.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
});


// ─── Preservation: Diagnose Submission (Req 3.3) ──────────────────────────────

describe('Preservation — Diagnose submission behavior (Req 3.3)', () => {
  /**
   * **Validates: Requirements 3.3**
   *
   * Property: For all valid symptom inputs (≥3 chars), submitting symptoms
   * calls the API and renders diagnoses identically.
   */
  it('submitting symptoms calls API and renders diagnoses for any valid input', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          symptomText: fc.string({ minLength: 3, maxLength: 100 }).filter((s) => s.trim().length >= 3),
          conditionName: fc.string({ minLength: 1, maxLength: 50 }).filter((s) => s.trim().length > 0),
          probability: fc.double({ min: 0.01, max: 1.0, noNaN: true }),
        }),
        async ({ symptomText, conditionName, probability }) => {
          cleanup();
          vi.clearAllMocks();
          mockListAntibiotics.mockResolvedValue([]);

          const mockResponse = {
            sessionId: `diag-${Date.now()}`,
            diagnoses: [
              {
                condition: conditionName,
                probability,
                icdCode: 'J18',
                matchingSymptoms: [],
                concordantSymptoms: [],
              },
            ],
            sources: [],
          };

          mockGetSymptomsDiagnosis.mockResolvedValue(mockResponse);

          const { default: DiagnosePage } = await import('../page');
          render(<DiagnosePage />);

          const textarea = screen.getByRole('textbox');
          fireEvent.change(textarea, { target: { value: symptomText } });

          await act(async () => {
            fireEvent.submit(textarea.closest('form')!);
          });

          // API should be called
          await waitFor(() => {
            expect(mockGetSymptomsDiagnosis).toHaveBeenCalledOnce();
          });

          // The condition name should be rendered
          await waitFor(() => {
            expect(screen.getAllByText(conditionName).length).toBeGreaterThanOrEqual(1);
          });

          // Probability bar should be rendered
          const progressBars = screen.getAllByRole('progressbar');
          expect(progressBars.length).toBeGreaterThan(0);

          return true;
        },
      ),
      { numRuns: 5 },
    );
  });

  /**
   * **Validates: Requirements 3.3**
   *
   * Diagnose submission renders confidence score and warnings when present.
   */
  it('renders confidence score and warnings when present in response', async () => {
    const mockResponse = {
      sessionId: 'diag-conf-1',
      diagnoses: [
        {
          condition: 'Pneumonia',
          probability: 0.85,
          icdCode: 'J18',
          matchingSymptoms: ['fever', 'cough'],
          concordantSymptoms: ['fever', 'cough'],
        },
      ],
      llmUsed: 'gpt-4',
      sources: [],
      confidenceScore: 0.78,
      warningsPresent: true,
      fallbackWarning: 'Fallback LLM used',
    };

    mockGetSymptomsDiagnosis.mockResolvedValue(mockResponse);

    const { default: DiagnosePage } = await import('../page');
    render(<DiagnosePage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'fever and cough for 3 days' } });

    await act(async () => {
      fireEvent.submit(textarea.closest('form')!);
    });

    // Diagnosis should be rendered
    await waitFor(() => {
      expect(screen.getAllByText('Pneumonia').length).toBeGreaterThanOrEqual(1);
    });

    // Confidence score should be displayed
    await waitFor(() => {
      const scoreEl = screen.getByTestId('confidence-score');
      expect(scoreEl).toBeDefined();
      expect(scoreEl.textContent).toContain('78%');
    });

    // Warning banner should be visible
    const alerts = screen.getAllByRole('alert');
    expect(alerts.length).toBeGreaterThan(0);
  });
});
