import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

// Mock next-intl
vi.mock('next-intl', () => ({
  useTranslations: (ns: string) => (key: string) => `${ns}.${key}`,
  useLocale: () => 'en',
}));

// Mock AuthContext
vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', email: 'doc@test.com', role: 'doctor', fullName: 'Dr Test' } }),
}));

// Mock next/image
vi.mock('next/image', () => ({
  default: (props: Record<string, unknown>) => React.createElement('img', { ...props, fill: undefined }),
}));

// Mock next/link
vi.mock('next/link', () => ({
  default: ({ children, ...props }: { children: React.ReactNode; href: string }) => React.createElement('a', props, children),
}));

// Mock PrescriptionStep
vi.mock('../PrescriptionStep', () => ({
  PrescriptionStep: () => React.createElement('div', { 'data-testid': 'prescription-step' }),
}));

// Mock Toast
vi.mock('../../../../components/Toast', () => ({
  Toast: () => null,
}));

// Mock IMAGES
vi.mock('@/lib/images', () => ({
  IMAGES: { diagnoseHeader: { src: '/test.jpg', alt: 'test' } },
}));

// Build mock API client
const mockListMyConsultations = vi.fn();
const mockGetSession = vi.fn();
const mockGetSymptomsDiagnosis = vi.fn();
const mockListAntibiotics = vi.fn();
const mockListAllPatients = vi.fn();

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    diagnose: {
      listMyConsultations: mockListMyConsultations,
      getSession: mockGetSession,
      getSymptomsDiagnosis: mockGetSymptomsDiagnosis,
      listAntibiotics: mockListAntibiotics,
      getPrescription: vi.fn().mockResolvedValue({}),
    },
    patients: {
      listAllPatients: mockListAllPatients,
    },
    chat: {
      sendMessageStream: vi.fn(),
    },
  }),
}));

import DiagnosePage from '../page';

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  Element.prototype.scrollIntoView = vi.fn();

  vi.stubGlobal('IntersectionObserver', vi.fn(() => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  })));

  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });

  // Defaults
  mockListMyConsultations.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
  mockGetSession.mockRejectedValue(new Error('not found'));
  mockListAntibiotics.mockResolvedValue([]);
  mockListAllPatients.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
});

// ─── Test data helpers ────────────────────────────────────────────────────────

function makeConsultation(id: string, condition: string) {
  return {
    id,
    symptoms: [{ name: 'fever', severity: 'moderate', durationDays: 3 }],
    diagnoses: [{ condition, probability: 0.8, icdCode: 'B50', matchingSymptoms: ['fever'], concordantSymptoms: ['fever'] }],
    alerts: [],
    llmUsed: 'test',
    createdAt: '2025-01-01T00:00:00Z',
    isOneShot: false,
    agentContributions: [],
    evidenceCitations: [],
  };
}

function makeSession(id: string) {
  return {
    id,
    symptoms: [{ name: 'fever', severity: 'moderate', durationDays: 3 }],
    diagnoses: [{ condition: 'Malaria', probability: 0.8, icdCode: 'B50', matchingSymptoms: ['fever'], concordantSymptoms: ['fever'] }],
    prescription: undefined,
    alerts: [],
    createdAt: '2025-01-01T00:00:00Z',
  };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('DiagnosePage session history integration', () => {
  it('shows loading state while fetching consultations', async () => {
    // Make listMyConsultations hang
    let resolveList!: (v: unknown) => void;
    mockListMyConsultations.mockReturnValue(new Promise((r) => { resolveList = r; }));

    const { container } = render(<DiagnosePage />);

    // The panel should show a loading indicator (aria-busy)
    const busy = container.querySelector('[aria-busy="true"]');
    expect(busy).not.toBeNull();

    // Resolve to clean up
    await act(async () => {
      resolveList({ items: [], total: 0, page: 1, pageSize: 20 });
    });
  });

  it('shows error state on fetch failure', async () => {
    mockListMyConsultations.mockRejectedValue(new Error('Network error'));

    const { findByText } = render(<DiagnosePage />);

    const errorMsg = await findByText('sessionHistory.errorFetch');
    expect(errorMsg).toBeDefined();
  });

  it('shows empty state when no consultations', async () => {
    mockListMyConsultations.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });

    const { findByText } = render(<DiagnosePage />);

    const emptyMsg = await findByText('sessionHistory.emptyDiagnose');
    expect(emptyMsg).toBeDefined();
  });

  it('clicking entry loads consultation results', async () => {
    mockListMyConsultations.mockResolvedValue({
      items: [makeConsultation('cons-1', 'Malaria'), makeConsultation('cons-2', 'Dengue')],
      total: 2,
      page: 1,
      pageSize: 20,
    });

    mockGetSession.mockImplementation((id: string) => {
      if (id === 'cons-1') return Promise.resolve(makeSession('cons-1'));
      return Promise.reject(new Error('not found'));
    });

    const { findByTestId } = render(<DiagnosePage />);

    // Wait for consultations to load and click the first entry
    const entry = await findByTestId('session-entry-cons-1');
    await act(async () => {
      fireEvent.click(entry);
    });

    // Wait for getSession to be called
    await waitFor(() => {
      expect(mockGetSession).toHaveBeenCalledWith('cons-1');
    });
  });

  it('hide button removes entry from list without confirmation', async () => {
    mockListMyConsultations.mockResolvedValue({
      items: [makeConsultation('cons-1', 'Malaria'), makeConsultation('cons-2', 'Dengue')],
      total: 2,
      page: 1,
      pageSize: 20,
    });

    const { findByTestId, queryByTestId, container } = render(<DiagnosePage />);

    // Wait for entries to load
    await findByTestId('session-entry-cons-1');

    // Click the hide button on cons-1
    const hideBtn = await findByTestId('delete-btn-cons-1');
    await act(async () => {
      fireEvent.click(hideBtn);
    });

    // No confirmation dialog should appear
    const dialog = container.querySelector('[role="alertdialog"]');
    expect(dialog?.getAttribute('aria-modal')).not.toBe('true');

    // Entry should be removed from the list
    await waitFor(() => {
      expect(queryByTestId('session-entry-cons-1')).toBeNull();
    });

    // cons-2 should still be visible
    expect(queryByTestId('session-entry-cons-2')).not.toBeNull();
  });

  it('hidden consultation reappears on remount', async () => {
    mockListMyConsultations.mockResolvedValue({
      items: [makeConsultation('cons-1', 'Malaria')],
      total: 1,
      page: 1,
      pageSize: 20,
    });

    // First render
    const { findByTestId, queryByTestId, unmount } = render(<DiagnosePage />);

    // Wait for entry to load
    await findByTestId('session-entry-cons-1');

    // Hide the entry
    const hideBtn = await findByTestId('delete-btn-cons-1');
    await act(async () => {
      fireEvent.click(hideBtn);
    });

    // Verify it's gone
    await waitFor(() => {
      expect(queryByTestId('session-entry-cons-1')).toBeNull();
    });

    // Unmount
    unmount();

    // Re-render — the hidden entry should reappear since hiddenIds is component state only
    const { findByTestId: findByTestId2 } = render(<DiagnosePage />);
    const reappeared = await findByTestId2('session-entry-cons-1');
    expect(reappeared).toBeDefined();
  });

  it('new diagnosis prepends to list', async () => {
    mockListMyConsultations.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });

    mockGetSymptomsDiagnosis.mockResolvedValue({
      sessionId: 'new-cons-1',
      diagnoses: [{ condition: 'Typhoid', probability: 0.7, icdCode: 'A01', matchingSymptoms: ['fever'], concordantSymptoms: ['fever'] }],
      confidenceScore: 0.7,
      llmUsed: 'test',
      sources: [],
      warningsPresent: false,
      fallbackWarning: undefined,
      degradedWarning: undefined,
      parseFailed: false,
      agentContributions: [],
      evidenceCitations: [],
    });

    const { findByText, findByTestId, container } = render(<DiagnosePage />);

    // Wait for empty state
    await findByText('sessionHistory.emptyDiagnose');

    // Type symptoms in the textarea
    const textarea = container.querySelector('textarea')!;
    await act(async () => {
      fireEvent.change(textarea, { target: { value: 'fever and headache' } });
    });

    // Submit the form
    const submitBtn = container.querySelector('button[type="submit"]')!;
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    // Wait for the new consultation to appear in the session list
    const newEntry = await findByTestId('session-entry-new-cons-1');
    expect(newEntry).toBeDefined();
  });
});
