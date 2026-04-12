// Feature: diagno-pilot-improvements, Property 13: Validation formulaire — weight_kg doit être positif
/**
 * **Validates: Requirements 13**
 * Property 13: For any value weight_kg ≤ 0 submitted in CreatePatientModal,
 * validation must fail and display an inline error message, without clearing other fields.
 */
import fc from 'fast-check';
import { describe, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import React from 'react';
import PatientsPage from '../../app/[locale]/patients/page';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'fr-TG',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
  usePathname: () => '/',
}));

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: '1', email: 'test@test.com' }, isLoading: false }),
}));

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    patients: {
      listPatients: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
      createPatient: vi.fn().mockResolvedValue({ id: '1', fullName: 'Test', allergies: [] }),
    },
  }),
}));

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
});

describe('CreatePatientModal — Property 13', () => {
  it('shows inline error for weight_kg ≤ 0 and does not clear other fields', { timeout: 30_000 }, async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.oneof(
          fc.constant('0'),
          fc.constant('-1'),
          fc.integer({ max: -1 }).map(String)
        ),
        async (invalidWeight) => {
          cleanup();
          render(<PatientsPage />);

          // Open the modal via the "+ new" button
          const newButton = screen.getByRole('button', { name: /new/i });
          fireEvent.click(newButton);

          // Fill in fullName with a valid value (query by name attribute)
          const fullNameInput = document.querySelector<HTMLInputElement>('input[name="fullName"]')!;
          fireEvent.change(fullNameInput, { target: { value: 'Jean Dupont' } });

          // Enter an invalid weight (≤ 0)
          const weightInput = document.querySelector<HTMLInputElement>('input[name="weightKg"]')!;
          fireEvent.change(weightInput, { target: { value: invalidWeight } });
          fireEvent.blur(weightInput);

          // Wait for the validation error to appear
          await waitFor(() => {
            const alerts = screen.queryAllByRole('alert');
            const weightError = alerts.find(
              (el) => el.textContent === 'Le poids doit être un nombre positif'
            );
            if (!weightError) throw new Error('Weight error not found yet');
          }, { timeout: 1000 });

          // Assert the error message is visible
          const alerts = screen.queryAllByRole('alert');
          const weightError = alerts.find(
            (el) => el.textContent === 'Le poids doit être un nombre positif'
          );
          if (!weightError) return false;

          // Assert fullName field still has its value (other fields not cleared)
          const fullNameValue = (document.querySelector<HTMLInputElement>('input[name="fullName"]') as HTMLInputElement).value;
          if (fullNameValue !== 'Jean Dupont') return false;

          return true;
        }
      ),
      { numRuns: 100 }
    );
  });
});
