/**
 * Bug condition exploration tests — RBAC Fix bugfix spec (Documents page)
 *
 * These tests assert the EXPECTED (correct) behavior and will FAIL on unfixed
 * code, proving each bug exists. DO NOT fix the code when these fail.
 *
 * **Validates: Requirements 1.2, 2.2**
 *
 * Bugs confirmed by this file:
 *   - Bug 3: Documents page accessible to infirmière without redirect
 *
 * Expected counterexamples (on unfixed code):
 *   - infirmière navigates to /documents → page renders without redirect
 *   - router.push is NOT called for infirmière (no role guard)
 */

import fc from 'fast-check';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
const mockRouter = { push: mockPush, replace: vi.fn(), back: vi.fn() };

vi.mock('next/navigation', () => ({
  useRouter: () => mockRouter,
  useParams: () => ({ locale: 'fr' }),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'fr',
}));

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    documents: {
      listDocuments: vi.fn().mockResolvedValue([]),
      deleteDocument: vi.fn().mockResolvedValue(undefined),
      uploadDocument: vi.fn().mockResolvedValue({}),
    },
  }),
}));

const mockAuthValue = {
  user: null as null | { id: string; email: string; role: string; fullName: string },
  isLoading: false,
  login: vi.fn(),
  logout: vi.fn(),
  fetchWithRefresh: vi.fn(),
};

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthValue,
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function renderDocumentsPage(role: string) {
  mockAuthValue.user = { id: '1', email: 'user@test.com', role, fullName: 'Test User' };
  mockAuthValue.isLoading = false;
  const { default: DocumentsPage } = await import('../page');
  return render(<DocumentsPage />);
}

beforeEach(() => {
  cleanup();
  mockPush.mockClear();
  mockAuthValue.user = null;
  mockAuthValue.isLoading = false;
});

// ─── Bug 3: Documents page accessible to infirmière without redirect ──────────

describe('Bug 3 — Documents page redirects infirmière', () => {
  /**
   * **Validates: Requirements 1.2, 2.2**
   * Documents page MUST redirect infirmière to home page.
   * EXPECTED TO FAIL on unfixed code — page renders without redirect for infirmière.
   * Counterexample: router.push is NOT called when role='infirmière'.
   */
  it('infirmière navigating to /documents triggers router.push (redirect)', async () => {
    await renderDocumentsPage('infirmière');
    // BUG 3: router.push is NOT called on unfixed code (no role guard)
    expect(mockPush).toHaveBeenCalled();
  });

  it('infirmière is redirected away from documents page (not to login)', async () => {
    await renderDocumentsPage('infirmière');
    // BUG 3: router.push is NOT called on unfixed code
    // When fixed, should redirect to home (not login)
    const calls = mockPush.mock.calls;
    expect(calls.length).toBeGreaterThan(0);
    // Should redirect to home, not login
    const redirectTarget = calls[0]?.[0] as string;
    expect(redirectTarget).not.toContain('/login');
  });
});

// ─── Property: all unauthorized roles trigger redirect on documents page ──────

describe('Property — unauthorized roles are redirected from documents page', () => {
  /**
   * **Validates: Requirements 1.2, 2.2**
   * For all unauthorized roles ['infirmière', 'guest'],
   * the documents page MUST redirect.
   *
   * EXPECTED TO FAIL on unfixed code — no role guard exists.
   * Counterexample: role='infirmière' → router.push not called.
   */
  it('infirmière is redirected from documents page (property test)', async () => {
    await fc.assert(
      fc.asyncProperty(fc.constant('infirmière'), async (role) => {
        cleanup();
        mockPush.mockClear();
        await renderDocumentsPage(role);
        const wasRedirected = mockPush.mock.calls.length > 0;
        cleanup();
        // BUG 3: wasRedirected is false on unfixed code
        return wasRedirected;
      }),
      { numRuns: 3 },
    );
  });

  it('guest is redirected from documents page (property test)', async () => {
    await fc.assert(
      fc.asyncProperty(fc.constant('guest'), async (role) => {
        cleanup();
        mockPush.mockClear();
        await renderDocumentsPage(role);
        const wasRedirected = mockPush.mock.calls.length > 0;
        cleanup();
        // BUG 3: wasRedirected is false on unfixed code for guest too
        return wasRedirected;
      }),
      { numRuns: 3 },
    );
  });

  it('authorized roles (admin, medecin) are NOT redirected from documents page', async () => {
    for (const role of ['admin', 'medecin']) {
      cleanup();
      mockPush.mockClear();
      await renderDocumentsPage(role);
      // admin and medecin should NOT be redirected
      expect(mockPush).not.toHaveBeenCalled();
      cleanup();
    }
  });
});
