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

// Build mock API client
const mockListSessions = vi.fn();
const mockGetHistory = vi.fn();
const mockDeleteSession = vi.fn();
const mockSendMessageStream = vi.fn();
const mockListAllPatients = vi.fn().mockResolvedValue([]);

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    chat: {
      listSessions: mockListSessions,
      getHistory: mockGetHistory,
      deleteSession: mockDeleteSession,
      sendMessageStream: mockSendMessageStream,
      submitFeedback: vi.fn(),
    },
    patients: {
      listAllPatients: mockListAllPatients,
    },
  }),
}));

// Mock IntersectionObserver
const mockObserve = vi.fn();
const mockDisconnect = vi.fn();

import ChatPage from '../page';

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();

  // Mock scrollIntoView (not available in jsdom)
  Element.prototype.scrollIntoView = vi.fn();

  vi.stubGlobal('IntersectionObserver', vi.fn(() => ({
    observe: mockObserve,
    unobserve: vi.fn(),
    disconnect: mockDisconnect,
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

  // Default: listSessions returns empty, getHistory rejects (no stored session)
  mockListSessions.mockResolvedValue({ sessions: [] });
  mockGetHistory.mockRejectedValue(new Error('not found'));
});

afterEach(() => {
  cleanup();
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ChatPage session history integration', () => {
  it('shows loading state while fetching sessions', async () => {
    // Make listSessions hang
    let resolveList!: (v: unknown) => void;
    mockListSessions.mockReturnValue(new Promise((r) => { resolveList = r; }));

    const { container } = render(<ChatPage />);

    // The panel should show a loading indicator (aria-busy)
    const busy = container.querySelector('[aria-busy="true"]');
    expect(busy).not.toBeNull();

    // Resolve to clean up
    await act(async () => {
      resolveList({ sessions: [] });
    });
  });

  it('shows error state on fetch failure', async () => {
    mockListSessions.mockRejectedValue(new Error('Network error'));

    const { findByText } = render(<ChatPage />);

    const errorMsg = await findByText('sessionHistory.errorFetch');
    expect(errorMsg).toBeDefined();
  });

  it('shows empty state when no sessions', async () => {
    mockListSessions.mockResolvedValue({ sessions: [] });

    const { findByText } = render(<ChatPage />);

    const emptyMsg = await findByText('sessionHistory.empty');
    expect(emptyMsg).toBeDefined();
  });

  it('clicking entry loads session and updates localStorage', async () => {
    mockListSessions.mockResolvedValue({
      sessions: [
        { sessionId: 'sess-1', preview: 'Hello doctor', createdAt: '2025-01-01T00:00:00Z', updatedAt: '2025-01-02T00:00:00Z' },
        { sessionId: 'sess-2', preview: 'Second chat', createdAt: '2025-01-01T00:00:00Z', updatedAt: '2025-01-01T00:00:00Z' },
      ],
    });

    mockGetHistory.mockImplementation((id: string) => {
      if (id === 'sess-1') {
        return Promise.resolve({
          id: 'sess-1',
          messages: [
            { id: 'msg-1', role: 'user', content: 'Hello doctor', timestamp: '2025-01-01T00:00:00Z' },
            { id: 'msg-2', role: 'assistant', content: 'How can I help?', timestamp: '2025-01-01T00:00:01Z' },
          ],
          createdAt: '2025-01-01T00:00:00Z',
        });
      }
      return Promise.reject(new Error('not found'));
    });

    const { findByTestId } = render(<ChatPage />);

    // Wait for sessions to load and click the first entry
    const entry = await findByTestId('session-entry-sess-1');
    await act(async () => {
      fireEvent.click(entry);
    });

    // Wait for getHistory to be called
    await waitFor(() => {
      expect(mockGetHistory).toHaveBeenCalledWith('sess-1');
    });

    // localStorage should be updated
    expect(localStorage.getItem('diagno-pilot-chat-session')).toBe('sess-1');
  });

  it('deleting active session clears chat and starts new session', async () => {
    // Set up localStorage with active session
    localStorage.setItem('diagno-pilot-chat-session', 'sess-active');

    mockListSessions.mockResolvedValue({
      sessions: [
        { sessionId: 'sess-active', preview: 'Active chat', createdAt: '2025-01-01T00:00:00Z', updatedAt: '2025-01-02T00:00:00Z' },
      ],
    });

    // getHistory for the stored session
    mockGetHistory.mockResolvedValue({
      id: 'sess-active',
      messages: [
        { id: 'msg-1', role: 'user', content: 'Active chat', timestamp: '2025-01-01T00:00:00Z' },
      ],
      createdAt: '2025-01-01T00:00:00Z',
    });

    mockDeleteSession.mockResolvedValue({ detail: 'Session deleted' });

    const { findByTestId, container } = render(<ChatPage />);

    // Wait for sessions to load
    const entry = await findByTestId('session-entry-sess-active');

    // First, click the entry to make it the active session
    await act(async () => {
      fireEvent.click(entry);
    });

    await waitFor(() => {
      expect(mockGetHistory).toHaveBeenCalledWith('sess-active');
    });

    // Now click the delete button
    const deleteBtn = await findByTestId('delete-btn-sess-active');
    await act(async () => {
      fireEvent.click(deleteBtn);
    });

    // Confirm dialog should appear — find and click the confirm button
    const confirmBtn = container.querySelector('[role="alertdialog"] button.bg-red-600');
    expect(confirmBtn).not.toBeNull();
    await act(async () => {
      fireEvent.click(confirmBtn!);
    });

    // deleteSession should be called
    await waitFor(() => {
      expect(mockDeleteSession).toHaveBeenCalledWith('sess-active');
    });

    // localStorage should be cleared (new session generated)
    const storedId = localStorage.getItem('diagno-pilot-chat-session');
    expect(storedId).toBeNull();
  });

  it('SSE done event upserts session in list', async () => {
    mockListSessions.mockResolvedValue({ sessions: [] });
    // getHistory for the initial stored session — reject so it starts fresh
    mockGetHistory.mockRejectedValue(new Error('not found'));

    // Create an async generator that yields a done event
    async function* fakeStream() {
      yield {
        type: 'done' as const,
        answer: 'AI response',
        session_id: 'sse-session-1',
        sources: [],
        llm_used: 'test',
        fallback_warning: null,
        warnings_present: false,
      };
    }
    mockSendMessageStream.mockReturnValue(fakeStream());

    const { findByText, container } = render(<ChatPage />);

    // Wait for empty state to appear (sessions loaded)
    await findByText('sessionHistory.empty');

    // Type a message and send
    const textarea = container.querySelector('textarea')!;
    await act(async () => {
      fireEvent.change(textarea, { target: { value: 'Hello AI' } });
    });

    const sendBtn = container.querySelector('button[aria-label="chat.send"]')!;
    await act(async () => {
      fireEvent.click(sendBtn);
    });

    // Wait for the session to appear in the panel
    await waitFor(() => {
      const sessionEntry = container.querySelector('[data-testid="session-entry-sse-session-1"]');
      expect(sessionEntry).not.toBeNull();
    });
  });
});
