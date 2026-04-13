/**
 * Unit tests for Patients Page UX improvements.
 *
 * Validates:
 * - Req 4.1: i18n — all user-visible strings through i18n system
 * - Req 4.2: Spinner overlay and disabled inputs during form submission
 * - Req 4.3: Client-side search filtering by patient name
 * - Req 4.4: Unsaved changes ConfirmDialog on modal close
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// ─── Mocks (must be before component import) ─────────────────────────────────

// Stable translation function to avoid re-creating on every render
// (prevents useCallback/useMemo invalidation in the component)
const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params) return `${key}:${JSON.stringify(params)}`;
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', email: 'test@test.com', fullName: 'Dr Test', role: 'medecin' },
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => new URLSearchParams(),
}));

const mockListPatients = vi.fn();
const mockCreatePatient = vi.fn();
vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    patients: {
      listPatients: mockListPatients,
      createPatient: mockCreatePatient,
    },
  }),
}));

// Mock ConfirmDialog to make it testable
vi.mock('../components/ConfirmDialog', () => ({
  ConfirmDialog: ({ open, title, message, confirmLabel, cancelLabel, onConfirm, onCancel }: any) => {
    if (!open) return null;
    return (
      <div data-testid="confirm-dialog">
        <p data-testid="confirm-dialog-title">{title}</p>
        <p data-testid="confirm-dialog-message">{message}</p>
        <button data-testid="confirm-dialog-confirm" onClick={onConfirm}>{confirmLabel}</button>
        <button data-testid="confirm-dialog-cancel" onClick={onCancel}>{cancelLabel}</button>
      </div>
    );
  },
}));

// Mock other components
vi.mock('../components/Pagination', () => ({ default: () => <div data-testid="pagination" /> }));
vi.mock('../components/Toast', () => ({ Toast: ({ message }: { message: string }) => <div data-testid="toast">{message}</div> }));
vi.mock('../components/SkeletonLoader', () => ({ default: () => <div data-testid="skeleton" /> }));
vi.mock('../components/EmptyState', () => ({ default: ({ title, description }: { title: string; description?: string }) => <div data-testid="empty-state"><p>{title}</p>{description && <p>{description}</p>}</div> }));
vi.mock('@/lib/images', () => ({ IMAGES: { patientsEmpty: { src: '/test.png', alt: 'test' } } }));
vi.mock('@diagno-pilot/ui', () => ({ buttonVariants: { primary: 'btn-primary', secondary: 'btn-secondary' } }));

// ─── Import component under test (after mocks) ───────────────────────────────

import PatientsPage from '../app/[locale]/patients/page';

// ─── Test data ────────────────────────────────────────────────────────────────

const testPatients = [
  { id: '1', fullName: 'Alice Dupont', allergies: [], renalFailure: false, hepaticFailure: false, currentMedications: [] },
  { id: '2', fullName: 'Bob Martin', allergies: ['penicillin'], renalFailure: false, hepaticFailure: false, currentMedications: [] },
  { id: '3', fullName: 'Charlie Durand', allergies: [], renalFailure: true, hepaticFailure: false, currentMedications: [] },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function waitForPatientsLoaded() {
  await waitFor(() => {
    expect(screen.getByText('Alice Dupont')).toBeInTheDocument();
  });
}

async function openModal() {
  const newButton = screen.getByText(/new/);
  fireEvent.click(newButton);
  await waitFor(() => {
    expect(screen.getByText('createTitle')).toBeInTheDocument();
  });
}

function getFullNameInput(): HTMLInputElement {
  const inputs = screen.getAllByRole('textbox');
  const input = inputs.find((el) => (el as HTMLInputElement).name === 'fullName');
  if (!input) throw new Error('fullName input not found');
  return input as HTMLInputElement;
}

/**
 * Simulate typing into a react-hook-form registered input.
 * We need to set nativeInputValueSetter + dispatch input event
 * so that react-hook-form's onChange handler fires properly.
 */
function typeInInput(input: HTMLInputElement, value: string) {
  // Use the native setter to bypass React's synthetic event system
  const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    'value'
  )?.set;
  nativeInputValueSetter?.call(input, value);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

// ─── Setup / Teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  mockListPatients.mockResolvedValue({ items: [], total: 0 });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('Patients Page Improvements', () => {
  describe('Search Filtering (Req 4.3)', () => {
    beforeEach(() => {
      mockListPatients.mockResolvedValue({ items: testPatients, total: 3 });
    });

    it('renders search input when patients are loaded', async () => {
      render(<PatientsPage />);
      await waitForPatientsLoaded();
      expect(screen.getByLabelText('search')).toBeInTheDocument();
    });

    it('filters patients by name when typing in search input', async () => {
      render(<PatientsPage />);
      await waitForPatientsLoaded();

      const searchInput = screen.getByLabelText('search');
      fireEvent.change(searchInput, { target: { value: 'Alice' } });

      await waitFor(() => {
        expect(screen.getByText('Alice Dupont')).toBeInTheDocument();
        expect(screen.queryByText('Bob Martin')).not.toBeInTheDocument();
        expect(screen.queryByText('Charlie Durand')).not.toBeInTheDocument();
      });
    });

    it('shows "noResults" message when search matches nothing', async () => {
      render(<PatientsPage />);
      await waitForPatientsLoaded();

      const searchInput = screen.getByLabelText('search');
      fireEvent.change(searchInput, { target: { value: 'zzzzz' } });

      await waitFor(() => {
        expect(screen.getByText('noResults')).toBeInTheDocument();
      });
    });

    it('shows all patients when search query is empty', async () => {
      render(<PatientsPage />);
      await waitForPatientsLoaded();

      // With no search query, all patients should be visible
      expect(screen.getByText('Alice Dupont')).toBeInTheDocument();
      expect(screen.getByText('Bob Martin')).toBeInTheDocument();
      expect(screen.getByText('Charlie Durand')).toBeInTheDocument();
    });
  });

  describe('i18n (Req 4.1)', () => {
    it('renders "createNurse" i18n key instead of hardcoded French text', async () => {
      mockListPatients.mockResolvedValue({ items: testPatients, total: 3 });
      render(<PatientsPage />);
      await waitForPatientsLoaded();
      expect(screen.getByText(/createNurse/)).toBeInTheDocument();
    });

    it('renders "emptyDescription" i18n key in empty state', async () => {
      mockListPatients.mockResolvedValue({ items: [], total: 0 });
      render(<PatientsPage />);

      await waitFor(() => {
        const emptyState = screen.getByTestId('empty-state');
        expect(emptyState).toBeInTheDocument();
        expect(emptyState.textContent).toContain('emptyDescription');
      });
    });
  });

  describe('Spinner Overlay (Req 4.2)', () => {
    it('shows spinner overlay when form is submitting', async () => {
      mockListPatients.mockResolvedValue({ items: testPatients, total: 3 });
      mockCreatePatient.mockReturnValue(new Promise(() => {}));

      render(<PatientsPage />);
      await waitForPatientsLoaded();
      await openModal();

      const fullNameInput = getFullNameInput();
      typeInInput(fullNameInput, 'Test Patient');

      const saveButton = screen.getByText('save');
      fireEvent.click(saveButton);

      await waitFor(() => {
        expect(screen.getByTestId('spinner-overlay')).toBeInTheDocument();
      });
    });

    it('disables form inputs when submitting', async () => {
      mockListPatients.mockResolvedValue({ items: testPatients, total: 3 });
      mockCreatePatient.mockReturnValue(new Promise(() => {}));

      render(<PatientsPage />);
      await waitForPatientsLoaded();
      await openModal();

      const fullNameInput = getFullNameInput();
      typeInInput(fullNameInput, 'Test Patient');

      const saveButton = screen.getByText('save');
      fireEvent.click(saveButton);

      await waitFor(() => {
        expect(fullNameInput).toBeDisabled();
      });
    });
  });

  describe('Unsaved Changes Dialog (Req 4.4)', () => {
    it('shows ConfirmDialog when closing modal with dirty form', async () => {
      mockListPatients.mockResolvedValue({ items: testPatients, total: 3 });

      render(<PatientsPage />);
      await waitForPatientsLoaded();
      await openModal();

      const fullNameInput = getFullNameInput();
      typeInInput(fullNameInput, 'Dirty data');

      // Wait for react-hook-form to process the dirty state
      await waitFor(() => {
        expect(fullNameInput.value).toBe('Dirty data');
      });

      // Click the ✕ close button
      const closeButton = screen.getByLabelText('cancel');
      fireEvent.click(closeButton);

      // ConfirmDialog should appear
      await waitFor(() => {
        expect(screen.getByTestId('confirm-dialog')).toBeInTheDocument();
        expect(screen.getByTestId('confirm-dialog-title').textContent).toBe('unsavedChanges');
        expect(screen.getByTestId('confirm-dialog-message').textContent).toBe('unsavedChangesMessage');
      });
    });

    it('does NOT show ConfirmDialog when closing modal with clean form', async () => {
      mockListPatients.mockResolvedValue({ items: testPatients, total: 3 });

      render(<PatientsPage />);
      await waitForPatientsLoaded();
      await openModal();

      // Click the ✕ close button without making changes
      const closeButton = screen.getByLabelText('cancel');
      fireEvent.click(closeButton);

      // Modal should close, no ConfirmDialog
      await waitFor(() => {
        expect(screen.queryByText('createTitle')).not.toBeInTheDocument();
      });
      expect(screen.queryByTestId('confirm-dialog')).not.toBeInTheDocument();
    });

    it('closes modal when confirming discard in ConfirmDialog', async () => {
      mockListPatients.mockResolvedValue({ items: testPatients, total: 3 });

      render(<PatientsPage />);
      await waitForPatientsLoaded();
      await openModal();

      const fullNameInput = getFullNameInput();
      typeInInput(fullNameInput, 'Dirty data');

      await waitFor(() => {
        expect(fullNameInput.value).toBe('Dirty data');
      });

      // Click the ✕ close button
      const closeButton = screen.getByLabelText('cancel');
      fireEvent.click(closeButton);

      // ConfirmDialog should appear
      await waitFor(() => {
        expect(screen.getByTestId('confirm-dialog')).toBeInTheDocument();
      });

      // Click confirm to discard changes
      const confirmButton = screen.getByTestId('confirm-dialog-confirm');
      fireEvent.click(confirmButton);

      // Modal should close
      await waitFor(() => {
        expect(screen.queryByText('createTitle')).not.toBeInTheDocument();
      });
    });
  });
});
