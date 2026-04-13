/**
 * Page-level tests for PatientDetailPage
 * Validates: Requirements 7.5
 *
 * Includes:
 *   - Subtask 10.1: Property 10 — Patient detail page renders all required fields
 *
 * Strategy: PatientDetailPage uses React 19's use(params) which suspends in jsdom.
 * We test the page's rendering logic by creating a thin wrapper that provides
 * the resolved params synchronously, bypassing the Suspense issue.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import React from 'react';
import fc from 'fast-check';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockGetPatient = vi.fn();
const mockListConsultations = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'fr',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'doc@test.com', role: 'medecin', fullName: 'Dr Test' },
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    patients: {
      getPatient: mockGetPatient,
      listConsultations: mockListConsultations,
    },
    files: {
      getFileUrl: vi.fn(),
      uploadFile: vi.fn(),
    },
  }),
}));

// Mock global fetch for the files endpoint
global.fetch = vi.fn().mockResolvedValue({
  ok: true,
  json: () => Promise.resolve([]),
} as Response);

// ─── Inner component test wrapper ─────────────────────────────────────────────
// We test the inner rendering logic directly by importing the page module
// and creating a wrapper that provides params as a never-pending Promise
// that React's use() can resolve synchronously via its internal cache.

/**
 * Creates a synchronous thenable that React 19's use() hook can resolve
 * without suspending. A synchronous thenable calls its .then callback
 * immediately (synchronously), so React can get the value without suspending.
 */
function makeSyncParams(id: string): Promise<{ locale: string; id: string }> {
  const value = { locale: 'fr', id };
  // Create a synchronous thenable - React 19's use() handles these without suspending
  const syncThenable = {
    then(resolve: (v: typeof value) => void) {
      resolve(value);
    },
    // Make it look like a Promise for TypeScript
    catch: () => syncThenable,
    finally: () => syncThenable,
    [Symbol.toStringTag]: 'Promise',
  } as unknown as Promise<typeof value>;
  return syncThenable;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockListConsultations.mockResolvedValue([]);
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
    ok: true,
    json: () => Promise.resolve([]),
  });
});

/**
 * Helper: renders the PatientDetailPage with a pre-resolved params Promise.
 * We flush the microtask queue before rendering so the Promise is already
 * in "fulfilled" state when React's use() encounters it.
 */
async function renderPatientDetailPage(
  id: string,
  PatientDetailPage: React.ComponentType<{ params: Promise<{ locale: string; id: string }> }>
) {
  const params = makeSyncParams(id);

  render(
    <React.Suspense fallback={<div data-testid="loading">Loading...</div>}>
      <PatientDetailPage params={params} />
    </React.Suspense>
  );
}

describe('PatientDetailPage — page-level tests', () => {
  it('renders patient name after data loads', async () => {
    mockGetPatient.mockResolvedValue({
      id: 'p1',
      fullName: 'Alice Martin',
      weightKg: 65,
      allergies: ['penicillin'],
      renalFailure: false,
      hepaticFailure: false,
      currentMedications: [],
    });

    const { default: PatientDetailPage } = await import('../[id]/page');
    await renderPatientDetailPage('p1', PatientDetailPage);

    await waitFor(() => {
      // Patient name appears in both breadcrumb and h1; use heading role for specificity
      expect(screen.getByRole('heading', { name: 'Alice Martin' })).toBeDefined();
    }, { timeout: 5000 });
  });

  it('renders patient weight label after data loads', async () => {
    mockGetPatient.mockResolvedValue({
      id: 'p1',
      fullName: 'Alice Martin',
      weightKg: 65,
      allergies: [],
      renalFailure: false,
      hepaticFailure: false,
      currentMedications: [],
    });

    const { default: PatientDetailPage } = await import('../[id]/page');
    await renderPatientDetailPage('p1', PatientDetailPage);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Alice Martin' })).toBeDefined();
    }, { timeout: 5000 });

    // The weight label is rendered via t('weight') which returns 'weight'
    expect(screen.getByText('weight')).toBeDefined();
  });

  it('renders patient allergies after data loads', async () => {
    mockGetPatient.mockResolvedValue({
      id: 'p1',
      fullName: 'Alice Martin',
      weightKg: 65,
      allergies: ['penicillin', 'sulfa'],
      renalFailure: false,
      hepaticFailure: false,
      currentMedications: [],
    });

    const { default: PatientDetailPage } = await import('../[id]/page');
    await renderPatientDetailPage('p1', PatientDetailPage);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Alice Martin' })).toBeDefined();
    }, { timeout: 5000 });

    expect(screen.getByText('penicillin')).toBeDefined();
    expect(screen.getByText('sulfa')).toBeDefined();
  });

  it('renders consultation history section after data loads', async () => {
    mockGetPatient.mockResolvedValue({
      id: 'p1',
      fullName: 'Alice Martin',
      weightKg: 65,
      allergies: [],
      renalFailure: false,
      hepaticFailure: false,
      currentMedications: [],
    });
    mockListConsultations.mockResolvedValue([
      {
        id: 'c1',
        createdAt: '2024-01-15T10:00:00Z',
        symptoms: [{ name: 'fever', severity: 'moderate', durationDays: 2 }],
        diagnoses: [{ condition: 'Flu', probability: 0.8, icdCode: 'J11' }],
        prescription: null,
        llmUsed: null,
      },
    ]);

    const { default: PatientDetailPage } = await import('../[id]/page');
    await renderPatientDetailPage('p1', PatientDetailPage);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Alice Martin' })).toBeDefined();
    }, { timeout: 5000 });

    // The consultations section heading is rendered via t('consultations')
    expect(screen.getByText('consultations')).toBeDefined();
  });
});

// ─── Property-based tests ─────────────────────────────────────────────────────

// Feature: testing-coverage, Property 10: Patient detail page renders all required fields
describe('PatientDetailPage — Property 10: Patient detail page renders all required fields', () => {
  it('renders full_name, weight, allergies, and consultation history for any valid patient', async () => {
    // **Validates: Requirements 7.5**
    // Import once outside the loop — dynamic imports are cached
    const { default: PatientDetailPage } = await import('../[id]/page');

    // Use a small numRuns to keep the test fast while still exercising the property.
    // Each iteration does a full async render + waitFor, so we keep it tight.
    // Use alphanumeric strings to avoid regex/DOM special character issues.
    const examples = fc.sample(
      fc.record({
        fullName: fc.stringMatching(/^[A-Za-z][A-Za-z0-9]{1,30}$/),
        weightKg: fc.float({ min: 1, max: 200, noNaN: true }),
        allergies: fc.array(
          fc.stringMatching(/^[A-Za-z][A-Za-z0-9]{1,15}$/),
          { minLength: 1, maxLength: 3 }
        ),
      }),
      5,
    );

    for (const { fullName, weightKg, allergies } of examples) {
      cleanup();
      vi.clearAllMocks();

      mockGetPatient.mockResolvedValue({
        id: 'p-test',
        fullName,
        weightKg,
        allergies,
        renalFailure: false,
        hepaticFailure: false,
        currentMedications: [],
      });
      mockListConsultations.mockResolvedValue([
        {
          id: 'c1',
          createdAt: '2024-01-15T10:00:00Z',
          symptoms: [{ name: 'fever', severity: 'moderate', durationDays: 2 }],
          diagnoses: [{ condition: 'Flu', probability: 0.8, icdCode: 'J11' }],
          prescription: null,
          llmUsed: null,
        },
      ]);
      (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([]),
      });

      await renderPatientDetailPage('p-test', PatientDetailPage);

      // Patient name appears in both breadcrumb and h1; use heading role for specificity
      await waitFor(() => {
        expect(screen.getByRole('heading', { name: fullName })).toBeDefined();
      }, { timeout: 5000 });

      expect(screen.getByText('weight')).toBeDefined();

      for (const allergy of allergies) {
        expect(screen.getByText(allergy, { exact: true })).toBeDefined();
      }

      expect(screen.getByText('consultations')).toBeDefined();
    }
  }, 60000);
});
