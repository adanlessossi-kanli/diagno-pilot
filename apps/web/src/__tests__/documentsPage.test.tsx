/**
 * Unit tests for the Documents page (/[locale]/documents).
 *
 * Covers:
 * - Access control redirect for unauthorized roles
 * - Responsive layout (sidebar visibility, mobile toggle)
 * - DocumentChat integration (chat input, send button, new session)
 * - DocumentSidebar integration (upload form, empty/error states)
 *
 * Requirements: 8.1, 12.1, 12.2
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import React from 'react';

// ─── Mock translations ────────────────────────────────────────────────────────

const mockTranslations: Record<string, string> = {
  // documentChat namespace
  title: 'Document Chat',
  placeholder: 'Ask a question about the documents...',
  send: 'Send',
  newSession: 'New session',
  thinking: 'Searching documents...',
  noDocuments: 'No documents indexed.',
  errorSend: 'Error sending message.',
  errorSendRetry: 'Error sending message.',
  retry: 'Retry',
  loadingHistory: 'Loading history...',
  sources: 'Sources',
  noInfoFound: 'No relevant information found.',
  // documentSidebar namespace
  uploadTitle: 'Upload Document',
  documentTitle: 'Document title',
  documentSource: 'Source',
  selectSource: 'Select a source',
  documentFile: 'File (PDF, DOCX, TXT, CSV)',
  upload: 'Upload',
  uploading: 'Uploading...',
  uploadSuccess: 'Document uploaded successfully.',
  errorUpload: 'Error uploading document.',
  documents: 'Indexed Documents',
  loadingDocuments: 'Loading documents...',
  errorFetch: 'Error loading documents.',
  errorDelete: 'Error deleting document.',
  confirmDelete: 'Delete this document?',
  download: 'Download',
  errorDownload: 'Error downloading document.',
  // sessionHistory namespace
  chatTitle: 'Chat History',
  empty: 'No sessions yet.',
  delete: 'Delete',
  sessionLoaded: 'Session loaded.',
  sessionDeleted: 'Session deleted.',
  errorLoad: 'Error loading session.',
};

// ─── Mocks (must be before imports that use them) ─────────────────────────────

// Mock next-intl
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => mockTranslations[key] ?? key,
  useLocale: () => 'en',
}));

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  useParams: () => ({ locale: 'en' }),
}));

// Mock AuthContext — control user role per test
let mockUser: { id: string; email: string; fullName: string; role: string } | null = null;
let mockAuthLoading = false;

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: mockUser,
    isLoading: mockAuthLoading,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

// Mock API client
const mockApiClient = {
  documents: {
    listDocuments: vi.fn().mockResolvedValue([]),
    uploadDocument: vi.fn(),
    deleteDocument: vi.fn(),
    chatStream: vi.fn(),
    listChatSessions: vi.fn().mockResolvedValue({ sessions: [] }),
    getChatHistory: vi.fn().mockResolvedValue(null),
    deleteChatSession: vi.fn(),
    getDownloadUrl: vi.fn(),
  },
  chat: {
    sendMessageStream: vi.fn(),
    getHistory: vi.fn(),
    listSessions: vi.fn().mockResolvedValue({ sessions: [] }),
    deleteSession: vi.fn(),
  },
  patients: {
    listAllPatients: vi.fn().mockResolvedValue([]),
  },
};

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => mockApiClient,
}));

// ─── Setup / Teardown ────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mockUser = { id: 'u1', email: 'admin@test.com', fullName: 'Admin', role: 'admin' };
  mockAuthLoading = false;
  Element.prototype.scrollIntoView = vi.fn();

  // Re-set default mock implementations (clearAllMocks resets them)
  mockApiClient.documents.listDocuments.mockResolvedValue([]);
  mockApiClient.documents.listChatSessions.mockResolvedValue({ sessions: [] });
  mockApiClient.documents.getChatHistory.mockResolvedValue(null);
  mockApiClient.chat.listSessions.mockResolvedValue({ sessions: [] });
  mockApiClient.patients.listAllPatients.mockResolvedValue([]);

  vi.stubGlobal(
    'IntersectionObserver',
    vi.fn(() => ({
      observe: vi.fn(),
      unobserve: vi.fn(),
      disconnect: vi.fn(),
    })),
  );

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
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ─── Import component under test (after mocks) ───────────────────────────────

import DocumentsPage from '../app/[locale]/documents/page';

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('Documents Page', () => {
  // ── Access Control ──────────────────────────────────────────────────────────

  describe('Access Control', () => {
    it('redirects pharmacien role to home page', () => {
      mockUser = { id: 'u1', email: 'pharm@test.com', fullName: 'Pharmacist', role: 'pharmacien' };
      render(<DocumentsPage />);
      expect(mockPush).toHaveBeenCalledWith('/en');
    });

    it('redirects guest role to home page', () => {
      mockUser = { id: 'u1', email: 'guest@test.com', fullName: 'Guest', role: 'guest' };
      render(<DocumentsPage />);
      expect(mockPush).toHaveBeenCalledWith('/en');
    });

    it('redirects unauthenticated users to home page', () => {
      mockUser = null;
      render(<DocumentsPage />);
      expect(mockPush).toHaveBeenCalledWith('/en');
    });

    it('renders page for admin role', () => {
      mockUser = { id: 'u1', email: 'admin@test.com', fullName: 'Admin', role: 'admin' };
      render(<DocumentsPage />);
      expect(mockPush).not.toHaveBeenCalled();
    });

    it('renders page for medecin role', () => {
      mockUser = { id: 'u1', email: 'doc@test.com', fullName: 'Doctor', role: 'medecin' };
      render(<DocumentsPage />);
      expect(mockPush).not.toHaveBeenCalled();
    });

    it('renders page for infirmière role', () => {
      mockUser = { id: 'u1', email: 'nurse@test.com', fullName: 'Nurse', role: 'infirmière' };
      render(<DocumentsPage />);
      expect(mockPush).not.toHaveBeenCalled();
    });

    it('shows loading state while auth is loading', () => {
      mockAuthLoading = true;
      mockUser = null;
      render(<DocumentsPage />);
      expect(screen.getByText('Loading…')).toBeTruthy();
    });
  });

  // ── Responsive Layout ──────────────────────────────────────────────────────

  describe('Responsive Layout', () => {
    it('renders sidebar container in the DOM', () => {
      mockUser = { id: 'u1', email: 'admin@test.com', fullName: 'Admin', role: 'admin' };
      const { container } = render(<DocumentsPage />);
      // The sidebar aside has class "hidden md:flex" — it exists in the DOM
      const sidebar = container.querySelector('aside.hidden.md\\:flex');
      expect(sidebar).toBeTruthy();
    });

    it('renders mobile toggle button', () => {
      mockUser = { id: 'u1', email: 'admin@test.com', fullName: 'Admin', role: 'admin' };
      const { container } = render(<DocumentsPage />);
      // The toggle button has class "md:hidden"
      const toggleBtn = container.querySelector('button.md\\:hidden');
      expect(toggleBtn).toBeTruthy();
    });

    it('opens mobile sidebar overlay when toggle is clicked', () => {
      mockUser = { id: 'u1', email: 'admin@test.com', fullName: 'Admin', role: 'admin' };
      const { container } = render(<DocumentsPage />);
      const toggleBtn = container.querySelector('button.md\\:hidden');
      expect(toggleBtn).toBeTruthy();
      fireEvent.click(toggleBtn!);
      // After clicking, a fixed overlay should appear
      const overlay = container.querySelector('.fixed.inset-0.z-50');
      expect(overlay).toBeTruthy();
    });
  });

  // ── DocumentChat Integration ───────────────────────────────────────────────

  describe('DocumentChat Integration', () => {
    it('renders chat input and send button', () => {
      mockUser = { id: 'u1', email: 'admin@test.com', fullName: 'Admin', role: 'admin' };
      render(<DocumentsPage />);
      const textarea = screen.getByPlaceholderText(mockTranslations.placeholder);
      expect(textarea).toBeTruthy();
      const sendButton = screen.getByRole('button', { name: mockTranslations.send });
      expect(sendButton).toBeTruthy();
    });

    it('renders "New session" button', () => {
      mockUser = { id: 'u1', email: 'admin@test.com', fullName: 'Admin', role: 'admin' };
      render(<DocumentsPage />);
      const newSessionBtn = screen.getByText(mockTranslations.newSession);
      expect(newSessionBtn).toBeTruthy();
    });

    it('renders Document Chat title', () => {
      mockUser = { id: 'u1', email: 'admin@test.com', fullName: 'Admin', role: 'admin' };
      render(<DocumentsPage />);
      expect(screen.getByText(mockTranslations.title)).toBeTruthy();
    });
  });

  // ── DocumentSidebar Integration ────────────────────────────────────────────

  describe('DocumentSidebar Integration', () => {
    it('renders upload form title', () => {
      mockUser = { id: 'u1', email: 'admin@test.com', fullName: 'Admin', role: 'admin' };
      render(<DocumentsPage />);
      // Upload title appears in the sidebar (may appear multiple times due to desktop + mobile)
      const uploadTitles = screen.getAllByText(mockTranslations.uploadTitle);
      expect(uploadTitles.length).toBeGreaterThanOrEqual(1);
    });

    it('shows empty state when no documents', async () => {
      mockApiClient.documents.listDocuments.mockResolvedValue([]);
      mockUser = { id: 'u1', email: 'admin@test.com', fullName: 'Admin', role: 'admin' };
      render(<DocumentsPage />);
      // Wait for the loading to finish and empty state to appear
      await waitFor(() => {
        const emptyMessages = screen.getAllByText(mockTranslations.noDocuments);
        expect(emptyMessages.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows error state when document fetch fails', async () => {
      mockApiClient.documents.listDocuments.mockRejectedValue(new Error('Network error'));
      mockUser = { id: 'u1', email: 'admin@test.com', fullName: 'Admin', role: 'admin' };
      render(<DocumentsPage />);
      await waitFor(() => {
        const errorMessages = screen.getAllByText(mockTranslations.errorFetch);
        expect(errorMessages.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('renders upload button', () => {
      mockUser = { id: 'u1', email: 'admin@test.com', fullName: 'Admin', role: 'admin' };
      render(<DocumentsPage />);
      const uploadButtons = screen.getAllByText(mockTranslations.upload);
      expect(uploadButtons.length).toBeGreaterThanOrEqual(1);
    });
  });
});
