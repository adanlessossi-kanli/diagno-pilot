// Feature: diagno-pilot-improvements, Property 12: Validation formulaire — texte libre de symptômes
/**
 * **Validates: Requirements 12**
 * Property 12: For any string of length strictly less than 3 (after trim),
 * the submit button of DiagnosePage must be disabled.
 */
import fc from 'fast-check';
import { describe, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';
import React from 'react';
import DiagnosePage from '../page';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('@/lib/images', () => ({
  IMAGES: {
    diagnoseHeader: {
      src: '/test-image.jpg',
      alt: 'Test image',
      source: 'https://example.com',
      licence: 'Test',
    },
  },
}));

vi.mock('next/image', () => ({
  default: ({ src, alt }: { src: string; alt: string }) => {
    return React.createElement('img', { src, alt });
  },
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'fr',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/',
}));

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: '1', email: 'test@test.com' } }),
}));

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    diagnose: {
      getSymptomsDiagnosis: vi.fn().mockResolvedValue({ diagnoses: [], sources: [] }),
      getPrescription: vi.fn().mockResolvedValue({ prescription: null, alerts: [] }),
      listAntibiotics: vi.fn().mockResolvedValue([]),
      listMyConsultations: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 }),
      getSession: vi.fn(),
    },
    patients: {
      listPatients: vi.fn().mockResolvedValue([]),
    },
  }),
}));

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
});

describe('DiagnosePage — Property 12', () => {
  it('submit button is disabled for any symptom text shorter than 3 chars', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ maxLength: 2 }),
        async (shortText) => {
          cleanup();
          render(<DiagnosePage />);

          const textarea = screen.getByRole('textbox');
          act(() => { fireEvent.change(textarea, { target: { value: shortText } }); });

          const submitButton = screen.getByRole('button', { name: /analyze/i });
          return (submitButton as HTMLButtonElement).disabled === true;
        }
      ),
      { numRuns: 100 }
    );
  });
});
