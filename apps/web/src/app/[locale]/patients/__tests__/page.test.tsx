/**
 * Page-level tests for PatientsPage
 * Validates: Requirements 7.3, 7.4
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockListPatients = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'fr-TG',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
  usePathname: () => '/patients',
}));

vi.mock('next/image', () => ({
  default: ({ src, alt }: { src: string; alt: string }) =>
    React.createElement('img', { src, alt }),
}));

vi.mock('@/lib/images', () => ({
  IMAGES: {
    patientsEmpty: { src: '/patients-empty.jpg', alt: 'No patients' },
  },
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
      listPatients: mockListPatients,
      createPatient: vi.fn(),
    },
  }),
}));

vi.mock('@diagno-pilot/ui', () => ({
  buttonVariants: { primary: 'btn-primary', secondary: 'btn-secondary' },
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

const mockPatients = [
  {
    id: 'p1',
    fullName: 'Alice Martin',
    dateOfBirth: '1990-01-01',
    allergies: [],
    renalFailure: false,
    hepaticFailure: false,
    currentMedications: [],
  },
  {
    id: 'p2',
    fullName: 'Bob Dupont',
    dateOfBirth: '1985-06-15',
    allergies: ['penicillin'],
    renalFailure: false,
    hepaticFailure: false,
    currentMedications: [],
  },
];

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('PatientsPage — page-level tests', () => {
  it('renders a loading skeleton while data is being fetched', async () => {
    // Never resolves during this test
    mockListPatients.mockReturnValue(new Promise(() => {}));
    const { default: PatientsPage } = await import('../page');
    render(<PatientsPage />);

    // SkeletonLoader renders with aria-busy="true" and aria-label="Loading"
    const skeleton = screen.getByLabelText('Loading');
    expect(skeleton).toBeDefined();
    expect(skeleton.getAttribute('aria-busy')).toBe('true');
  });

  it('renders patient cards after data resolves', async () => {
    mockListPatients.mockResolvedValue({ items: mockPatients, total: 2, page: 1, page_size: 20 });
    const { default: PatientsPage } = await import('../page');
    render(<PatientsPage />);

    await waitFor(() => {
      expect(screen.getByText('Alice Martin')).toBeDefined();
      expect(screen.getByText('Bob Dupont')).toBeDefined();
    });
  });

  it('renders empty state when API returns empty list', async () => {
    mockListPatients.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    const { default: PatientsPage } = await import('../page');
    render(<PatientsPage />);

    await waitFor(() => {
      // EmptyState renders the title from t('noPatients') which returns 'noPatients'
      expect(screen.getByText('noPatients')).toBeDefined();
    });
  });

  it('does not render patient cards when list is empty', async () => {
    mockListPatients.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    const { default: PatientsPage } = await import('../page');
    render(<PatientsPage />);

    await waitFor(() => {
      expect(screen.queryByText('Alice Martin')).toBeNull();
    });
  });
});
