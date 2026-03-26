/**
 * Unit test for PatientsPage empty state rendering the patientsEmpty image
 * Validates: Requirement 5.1
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import React from 'react';
import { IMAGES } from '@/lib/images';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

vi.mock('next/image', () => ({
  default: ({ src, alt }: { src: string; alt: string }) =>
    React.createElement('img', { src, alt }),
}));

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'doc@test.com', role: 'medecin', fullName: 'Dr Test' },
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

const mockListPatients = vi.fn();

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    patients: {
      listPatients: mockListPatients,
    },
  }),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

function mockApiToReturnEmptyList() {
  mockListPatients.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
}

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('PatientsPage — unit tests', () => {
  it('PatientsPage empty state renders IMAGES.patientsEmpty', async () => {
    mockApiToReturnEmptyList();
    const { default: PatientsPage } = await import('../page');
    render(<PatientsPage />);

    const img = await waitFor(() => screen.getByRole('img'));
    expect(img).toHaveAttribute('src', expect.stringContaining(IMAGES.patientsEmpty.src));
  });
});
