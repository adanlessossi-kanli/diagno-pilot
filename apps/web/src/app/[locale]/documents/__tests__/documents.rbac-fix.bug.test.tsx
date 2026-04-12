/**
 * RBAC tests — Documents page access control
 *
 * After the assistant-qa-and-documents-redesign, the Documents page allows
 * access to admin, medecin, AND infirmière (Req 12.1). Unauthorized roles
 * (pharmacien, guest) are redirected to the home page.
 *
 * **Validates: Requirements 12.1, 12.2**
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
      listChatSessions: vi.fn().mockResolvedValue({ sessions: [] }),
      getChatHistory: vi.fn().mockResolvedValue(null),
      deleteChatSession: vi.fn().mockResolvedValue(undefined),
      chatStream: vi.fn(),
      getDownloadUrl: vi.fn().mockResolvedValue({ url: '', filename: '', expires_in: 900, content_disposition: 'attachment' }),
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
  // Stub scrollIntoView for jsdom (used by DocumentChat)
  Element.prototype.scrollIntoView = vi.fn();
});

// ─── Unauthorized roles are redirected ────────────────────────────────────────

describe('Documents page — unauthorized roles are redirected', () => {
  /**
   * **Validates: Requirements 12.1, 12.2**
   * Unauthorized roles (pharmacien, guest) MUST be redirected from the documents page.
   */
  it('pharmacien is redirected from documents page', async () => {
    await renderDocumentsPage('pharmacien');
    expect(mockPush).toHaveBeenCalled();
  });

  it('guest is redirected from documents page', async () => {
    await renderDocumentsPage('guest');
    expect(mockPush).toHaveBeenCalled();
  });

  it('guest is redirected from documents page (property test)', async () => {
    await fc.assert(
      fc.asyncProperty(fc.constant('guest'), async (role) => {
        cleanup();
        mockPush.mockClear();
        await renderDocumentsPage(role);
        const wasRedirected = mockPush.mock.calls.length > 0;
        cleanup();
        return wasRedirected;
      }),
      { numRuns: 3 },
    );
  });
});

// ─── Authorized roles are NOT redirected ──────────────────────────────────────

describe('Documents page — authorized roles are NOT redirected', () => {
  /**
   * **Validates: Requirements 12.1, 12.2**
   * Authorized roles (admin, medecin, infirmière) MUST NOT be redirected.
   */
  it('authorized roles (admin, medecin, infirmière) are NOT redirected from documents page', async () => {
    for (const role of ['admin', 'medecin', 'infirmière']) {
      cleanup();
      mockPush.mockClear();
      await renderDocumentsPage(role);
      expect(mockPush).not.toHaveBeenCalled();
      cleanup();
    }
  });

  it('infirmière is NOT redirected from documents page (property test)', async () => {
    await fc.assert(
      fc.asyncProperty(fc.constant('infirmière'), async (role) => {
        cleanup();
        mockPush.mockClear();
        await renderDocumentsPage(role);
        const wasNotRedirected = mockPush.mock.calls.length === 0;
        cleanup();
        return wasNotRedirected;
      }),
      { numRuns: 3 },
    );
  });
});
