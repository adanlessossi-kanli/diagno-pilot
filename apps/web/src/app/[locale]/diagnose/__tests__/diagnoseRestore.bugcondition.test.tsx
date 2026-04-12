/**
 * Bug condition exploration tests — Diagnose Data Loss on Navigation
 *
 * These tests assert the EXPECTED (correct) behavior and will FAIL on unfixed
 * code, proving the bug exists. DO NOT fix the code or tests when they fail.
 *
 * **Validates: Requirements 1.2, 2.6, 2.7**
 *
 * Bug confirmed by this file:
 *   - Bug 1.2: Navigating away from the diagnose page after receiving results
 *     loses all diagnostic data because results are stored only in ephemeral
 *     useState with no persistence mechanism.
 *
 * Counterexamples found (documented after running on unfixed code):
 *   - DiagnosePage never writes sessionId to sessionStorage after diagnosis
 *   - DiagnosePage never reads from sessionStorage on mount
 *   - DiagnosePage never calls apiClient.diagnose.getSession to restore results
 *   - Unmounting and remounting the component loses all results
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockGetSymptomsDiagnosis = vi.fn();
const mockGetSession = vi.fn();
const mockGetPrescription = vi.fn();
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

const MOCK_USER = { id: 'user-42', email: 'doc@test.com', role: 'medecin', fullName: 'Dr Test' };

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: MOCK_USER,
    isLoading: false,
  }),
}));

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    diagnose: {
      getSymptomsDiagnosis: mockGetSymptomsDiagnosis,
      getSession: mockGetSession,
      getPrescription: mockGetPrescription,
      listAntibiotics: mockListAntibiotics,
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

// ─── Helpers ──────────────────────────────────────────────────────────────────

const SESSION_STORAGE_KEY = `diagno-pilot-diagnose-session-${MOCK_USER.id}`;

const mockDiagnosisResponse = {
  sessionId: 'diag-session-abc',
  diagnoses: [
    {
      condition: 'Malaria',
      probability: 0.85,
      icdCode: 'B50',
      matchingSymptoms: ['fever', 'chills'],
      concordantSymptoms: ['fever', 'chills'],
    },
    {
      condition: 'Typhoid',
      probability: 0.6,
      icdCode: 'A01',
      matchingSymptoms: ['fever'],
      concordantSymptoms: ['fever'],
    },
  ],
  llmUsed: 'qwen3',
  sources: [],
  confidenceScore: 0.78,
};

const mockDiagnoseSession = {
  id: 'diag-session-abc',
  symptoms: [{ name: 'fever and chills', severity: 'moderate', durationDays: 3 }],
  diagnoses: [
    { condition: 'Malaria', probability: 0.85, icdCode: 'B50', concordantSymptoms: ['fever', 'chills'] },
    { condition: 'Typhoid', probability: 0.6, icdCode: 'A01', concordantSymptoms: ['fever'] },
  ],
  alerts: [],
  createdAt: new Date().toISOString(),
};

/** Render DiagnosePage, submit symptoms, and wait for results */
async function renderAndSubmit() {
  const { default: DiagnosePage } = await import('../page');
  const { unmount } = render(<DiagnosePage />);

  const textarea = screen.getByRole('textbox');
  fireEvent.change(textarea, { target: { value: 'fever and chills for 3 days' } });

  await act(async () => {
    fireEvent.submit(textarea.closest('form')!);
  });

  await waitFor(() => {
    expect(screen.getAllByText('Malaria').length).toBeGreaterThanOrEqual(1);
  });

  return { unmount };
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  sessionStorage.clear();
  mockListAntibiotics.mockResolvedValue([]);
  mockGetSymptomsDiagnosis.mockResolvedValue(mockDiagnosisResponse);
  mockGetSession.mockResolvedValue(mockDiagnoseSession);
});

afterEach(() => {
  sessionStorage.clear();
});

// ─── Bug Condition: Diagnose Data Loss on Navigation ──────────────────────────

describe('Bug Condition — Diagnose data loss on navigation', () => {
  /**
   * **Validates: Requirement 2.6**
   *
   * EXPECTED behavior: After receiving diagnostic results, the session ID
   * should be persisted to sessionStorage (namespaced by user ID) so that
   * results can be restored on return.
   *
   * EXPECTED TO FAIL on unfixed code because DiagnosePage never writes
   * to sessionStorage after receiving results.
   *
   * Counterexample: results !== null, sessionId === 'diag-session-abc' →
   *   sessionStorage.getItem(key) returns null (never written).
   */
  it('stores session ID in sessionStorage after successful diagnosis', async () => {
    await renderAndSubmit();

    // EXPECTED: sessionStorage contains the session ID
    const stored = sessionStorage.getItem(SESSION_STORAGE_KEY);
    expect(stored).toBe('diag-session-abc');
  });

  /**
   * **Validates: Requirement 2.7**
   *
   * EXPECTED behavior: When the component remounts (simulating navigation
   * back), it should check sessionStorage for a stored session ID and
   * restore partial results from the backend via getSession.
   *
   * EXPECTED TO FAIL on unfixed code because:
   *   1. sessionStorage is never written to (so there's nothing to read)
   *   2. Even if we manually set sessionStorage, the component never reads it
   *   3. getSession is never called on mount
   */
  it('restores partial results from backend on remount after navigation', async () => {
    const { unmount } = await renderAndSubmit();

    // Verify results are displayed
    expect(screen.getAllByText('Malaria').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Typhoid').length).toBeGreaterThanOrEqual(1);

    // Simulate navigation away (unmount)
    unmount();
    cleanup();

    // Even if we manually set sessionStorage (to isolate the restore behavior),
    // the unfixed code won't read it
    sessionStorage.setItem(SESSION_STORAGE_KEY, 'diag-session-abc');

    // Simulate navigation back (remount)
    const { default: DiagnosePage } = await import('../page');
    render(<DiagnosePage />);

    // EXPECTED: getSession was called to restore results
    await waitFor(() => {
      expect(mockGetSession).toHaveBeenCalledWith('diag-session-abc');
    });

    // EXPECTED: restored diagnoses are displayed
    await waitFor(() => {
      expect(screen.getAllByText('Malaria').length).toBeGreaterThanOrEqual(1);
    });
  });

  /**
   * **Validates: Requirements 2.6, 2.7**
   *
   * Full round-trip test: submit → unmount → remount → verify restore.
   * This is the complete bug condition scenario.
   *
   * EXPECTED TO FAIL on unfixed code because neither sessionStorage write
   * nor restore-on-mount is implemented.
   */
  it('full round-trip: submit, navigate away, navigate back — results restored', async () => {
    const { unmount } = await renderAndSubmit();

    // Verify results are displayed after submission
    expect(screen.getAllByText('Malaria').length).toBeGreaterThanOrEqual(1);

    // EXPECTED: sessionStorage was written
    const storedBeforeUnmount = sessionStorage.getItem(SESSION_STORAGE_KEY);
    expect(storedBeforeUnmount).toBe('diag-session-abc');

    // Simulate navigation away
    unmount();
    cleanup();

    // Simulate navigation back
    const { default: DiagnosePage } = await import('../page');
    render(<DiagnosePage />);

    // EXPECTED: getSession was called with the stored session ID
    await waitFor(() => {
      expect(mockGetSession).toHaveBeenCalledWith('diag-session-abc');
    });

    // EXPECTED: diagnoses from the restored session are displayed
    await waitFor(() => {
      expect(screen.getAllByText('Malaria').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('Typhoid').length).toBeGreaterThanOrEqual(1);
    });
  });

  /**
   * **Validates: Requirement 2.7**
   *
   * EXPECTED behavior: When getSession fails on remount (e.g., session expired),
   * the component should handle it gracefully — clear sessionStorage and show
   * the empty form without blocking the user.
   *
   * EXPECTED TO FAIL on unfixed code because getSession is never called.
   */
  it('handles getSession failure gracefully on remount', async () => {
    // Manually set sessionStorage to simulate a stored session
    sessionStorage.setItem(SESSION_STORAGE_KEY, 'expired-session-xyz');

    // Mock getSession to fail
    mockGetSession.mockRejectedValueOnce({ status: 404, message: 'Session not found' });

    const { default: DiagnosePage } = await import('../page');
    render(<DiagnosePage />);

    // EXPECTED: getSession was called
    await waitFor(() => {
      expect(mockGetSession).toHaveBeenCalledWith('expired-session-xyz');
    });

    // EXPECTED: sessionStorage is cleared after failure
    await waitFor(() => {
      expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
    });

    // EXPECTED: the form is still usable (textarea is present)
    expect(screen.getByRole('textbox')).toBeDefined();
  });
});
