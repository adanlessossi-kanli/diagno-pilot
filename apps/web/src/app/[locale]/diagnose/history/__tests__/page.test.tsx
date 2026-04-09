/**
 * Tests for DiagnoseHistoryPage
 * Validates: Requirements 16.8, 16.9
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockListMyConsultations = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'fr',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/',
}));

vi.mock('../../../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'doc@test.com', role: 'medecin', fullName: 'Dr Test' },
    isLoading: false,
  }),
}));

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    diagnose: {
      listMyConsultations: mockListMyConsultations,
    },
  }),
}));

import DiagnoseHistoryPage from '../page';

// ─── Helpers ──────────────────────────────────────────────────────────────────

const mockConsultations = {
  items: [
    {
      id: 'c1',
      symptoms: [
        { name: 'fever', severity: 'moderate', durationDays: 3 },
        { name: 'cough', severity: 'mild', durationDays: 2 },
      ],
      diagnoses: [
        { condition: 'Pneumonia', probability: 0.85, concordantSymptoms: ['fever'] },
      ],
      alerts: [],
      llmUsed: 'gpt-4',
      createdAt: '2024-06-15T10:00:00Z',
      isOneShot: false,
    },
    {
      id: 'c2',
      symptoms: [
        { name: 'headache', severity: 'severe', durationDays: 1 },
      ],
      diagnoses: [
        { condition: 'Migraine', probability: 0.7, concordantSymptoms: ['headache'] },
      ],
      alerts: [],
      llmUsed: 'gpt-4',
      createdAt: '2024-06-14T08:00:00Z',
      isOneShot: true,
    },
  ],
  total: 25,
  page: 1,
  pageSize: 20,
};

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('DiagnoseHistoryPage — Paginated history (Req 16.8, 16.9)', () => {
  it('renders consultation history with symptoms, diagnosis, and date', async () => {
    mockListMyConsultations.mockResolvedValue(mockConsultations);

    await act(async () => {
      render(<DiagnoseHistoryPage />);
    });

    await waitFor(() => {
      expect(screen.getByText(/Pneumonia/)).toBeDefined();
    });

    expect(screen.getByText(/Migraine/)).toBeDefined();
    expect(screen.getByText(/fever, cough/)).toBeDefined();
    expect(screen.getByText(/headache/)).toBeDefined();
  });

  it('shows empty state when no consultations exist', async () => {
    mockListMyConsultations.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    });

    await act(async () => {
      render(<DiagnoseHistoryPage />);
    });

    await waitFor(() => {
      expect(screen.getByText('history.noHistory')).toBeDefined();
    });
  });

  it('enables Next button when more pages exist and Previous is disabled on page 1', async () => {
    mockListMyConsultations.mockResolvedValue(mockConsultations);

    await act(async () => {
      render(<DiagnoseHistoryPage />);
    });

    await waitFor(() => {
      expect(screen.getByText(/Pneumonia/)).toBeDefined();
    });

    const prevBtn = screen.getByTestId('prev-button') as HTMLButtonElement;
    const nextBtn = screen.getByTestId('next-button') as HTMLButtonElement;

    expect(prevBtn.disabled).toBe(true);
    expect(nextBtn.disabled).toBe(false);
  });

  it('navigates to next page when Next button is clicked', async () => {
    mockListMyConsultations.mockResolvedValue(mockConsultations);

    await act(async () => {
      render(<DiagnoseHistoryPage />);
    });

    await waitFor(() => {
      expect(screen.getByText(/Pneumonia/)).toBeDefined();
    });

    const nextBtn = screen.getByTestId('next-button');
    await act(async () => {
      fireEvent.click(nextBtn);
    });

    await waitFor(() => {
      expect(mockListMyConsultations).toHaveBeenCalledWith(2, 20);
    });
  });
});
