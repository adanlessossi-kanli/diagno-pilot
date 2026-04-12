/**
 * Bug condition exploration tests — Chat Data Loss on "New Chat"
 *
 * These tests assert the EXPECTED (correct) behavior and will FAIL on unfixed
 * code, proving the bug exists. DO NOT fix the code or tests when they fail.
 *
 * **Validates: Requirements 1.1, 2.1, 2.2, 2.3, 2.4, 2.5**
 *
 * Bug confirmed by this file:
 *   - Bug 1.1: Clicking "New Chat" when messages exist clears state synchronously
 *     without verifying backend persistence via getHistory.
 *
 * Counterexamples found (documented after running on unfixed code):
 *   - handleNewSession clears messages synchronously without calling getHistory
 *   - No verification call is made before clearing localStorage session ID
 *   - No error is shown when backend verification would fail (because it's never attempted)
 *   - No loading/verifying state is set (button is never disabled during verification)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockGetHistory = vi.fn();
const mockSendMessageStream = vi.fn();
const mockListSessions = vi.fn().mockResolvedValue({ sessions: [] });
const mockDeleteSession = vi.fn();

// jsdom doesn't implement scrollIntoView
window.HTMLElement.prototype.scrollIntoView = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'fr',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', email: 'doc@test.com', role: 'medecin', fullName: 'Dr Test' },
    isLoading: false,
  }),
}));

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    chat: {
      sendMessageStream: mockSendMessageStream,
      getHistory: mockGetHistory,
      listSessions: mockListSessions,
      deleteSession: mockDeleteSession,
      submitFeedback: vi.fn(),
    },
    patients: {
      listAllPatients: vi.fn().mockResolvedValue([]),
    },
  }),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Helper: create a stream that yields events then completes */
function mockStreamFromEvents(events: Array<{ type: string; content?: string; answer?: string; sources?: unknown[]; error?: string; retryable?: boolean }>) {
  return async function* () {
    for (const event of events) {
      yield event;
    }
  };
}

/** Helper: render ChatPage, send a message, wait for it to appear */
async function renderChatWithMessages() {
  mockSendMessageStream.mockImplementation(
    mockStreamFromEvents([
      { type: 'token', content: 'Response from assistant' },
      {
        type: 'done',
        answer: 'Response from assistant',
        sources: [],
      },
    ]),
  );

  const { default: ChatPage } = await import('../page');
  render(<ChatPage />);

  // Type and send a message to populate messages state
  const textarea = screen.getByRole('textbox');
  fireEvent.change(textarea, { target: { value: 'Patient has fever' } });

  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /send/i }));
  });

  // Wait for the assistant response to appear
  await waitFor(() => {
    expect(screen.getByText('Response from assistant')).toBeDefined();
  });

  return { textarea };
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();

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

  // Default: no stored session to restore
  mockGetHistory.mockResolvedValue(null);
});

// ─── Bug Condition: Chat Data Loss on "New Chat" (non-streaming) ──────────────

describe('Bug Condition — Chat data loss on "New Chat" (non-streaming)', () => {
  /**
   * **Validates: Requirements 2.1, 2.3**
   *
   * EXPECTED behavior: When user clicks "New Chat" with messages present and
   * no stream in progress, handleNewSession MUST call getHistory to verify
   * the session was persisted before clearing local state.
   *
   * EXPECTED TO FAIL on unfixed code because handleNewSession clears state
   * synchronously without any backend call.
   *
   * Counterexample: messages.length > 0, streaming === false →
   *   getHistory is never called, messages are cleared immediately.
   */
  it('calls getHistory to verify session before clearing when messages exist', async () => {
    // Mount won't call getHistory (no stored session in localStorage),
    // so the first mock value is consumed by the verification call
    mockGetHistory
      .mockResolvedValueOnce({ messages: [{ id: '1', role: 'user', content: 'fever', timestamp: new Date().toISOString() }] }); // verification call

    await renderChatWithMessages();

    // Click "New Chat"
    const newChatBtn = screen.getByRole('button', { name: /newSession/i });
    await act(async () => {
      fireEvent.click(newChatBtn);
    });

    // EXPECTED: getHistory was called for verification (mount call may or may not happen
    // depending on whether localStorage had a stored session — here it doesn't, so only 1 call)
    await waitFor(() => {
      expect(mockGetHistory.mock.calls.length).toBeGreaterThanOrEqual(1);
    });
  });

  /**
   * **Validates: Requirements 2.3**
   *
   * EXPECTED behavior: When getHistory confirms the session exists on the backend,
   * messages should be cleared and a new session started.
   *
   * EXPECTED TO FAIL on unfixed code because getHistory is never called.
   */
  it('clears messages only after getHistory confirms session exists', async () => {
    mockGetHistory
      .mockResolvedValueOnce({ messages: [{ id: '1', role: 'user', content: 'fever', timestamp: new Date().toISOString() }] }); // verification

    await renderChatWithMessages();

    // Verify messages are visible before clicking New Chat (may appear in session panel too)
    expect(screen.getAllByText('Patient has fever').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Response from assistant').length).toBeGreaterThanOrEqual(1);

    const newChatBtn = screen.getByRole('button', { name: /newSession/i });
    await act(async () => {
      fireEvent.click(newChatBtn);
    });

    // EXPECTED: getHistory was called for verification
    await waitFor(() => {
      expect(mockGetHistory.mock.calls.length).toBeGreaterThanOrEqual(1);
    });

    // After verification succeeds, chat messages should be cleared.
    // The assistant response should no longer appear anywhere in the DOM.
    await waitFor(() => {
      expect(screen.queryByText('Response from assistant')).toBeNull();
    });
  });

  /**
   * **Validates: Requirements 2.4**
   *
   * EXPECTED behavior: When getHistory fails (e.g., 404 or network error),
   * an error notification is shown and messages are NOT cleared.
   *
   * EXPECTED TO FAIL on unfixed code because getHistory is never called,
   * so the error path is never reached — messages are always cleared.
   */
  it('shows error and preserves messages when getHistory fails', async () => {
    mockGetHistory
      .mockRejectedValueOnce({ status: 404, message: 'Not found' }); // verification fails

    await renderChatWithMessages();

    expect(screen.getAllByText('Patient has fever').length).toBeGreaterThanOrEqual(1);

    const newChatBtn = screen.getByRole('button', { name: /newSession/i });
    await act(async () => {
      fireEvent.click(newChatBtn);
    });

    // EXPECTED: getHistory was called for verification
    await waitFor(() => {
      expect(mockGetHistory.mock.calls.length).toBeGreaterThanOrEqual(1);
    });

    // EXPECTED: error is displayed
    await waitFor(() => {
      const alerts = screen.queryAllByRole('alert');
      expect(alerts.length).toBeGreaterThan(0);
    });

    // EXPECTED: messages are preserved (not cleared) — assistant response still visible
    expect(screen.getAllByText('Response from assistant').length).toBeGreaterThanOrEqual(1);
  });

  /**
   * **Validates: Requirements 2.5**
   *
   * EXPECTED behavior: While the verification call is in flight, the "New Chat"
   * button should be disabled to prevent double-clicks.
   *
   * EXPECTED TO FAIL on unfixed code because there is no async verification,
   * so the button is never disabled.
   */
  it('disables New Chat button while verifying session', async () => {
    // Make getHistory hang (never resolve) to test the loading state
    let resolveVerification!: (value: unknown) => void;
    // Mount won't call getHistory (no stored session), so the first mock is for verification
    mockGetHistory
      .mockImplementationOnce(() => new Promise((resolve) => { resolveVerification = resolve; }));

    await renderChatWithMessages();

    const newChatBtn = screen.getByRole('button', { name: /newSession/i });

    // Click fires the async handler; flush microtasks so setVerifying(true) is applied
    await act(async () => {
      fireEvent.click(newChatBtn);
      // Allow the async handleNewSession to reach setVerifying(true)
      await new Promise((r) => setTimeout(r, 0));
    });

    // EXPECTED: button is disabled while verification is in flight
    await waitFor(() => {
      expect(newChatBtn).toHaveAttribute('disabled');
    });

    // Resolve the verification to clean up
    await act(async () => {
      resolveVerification({ messages: [] });
    });
  });
});

// ─── Bug Condition: Chat Data Loss on "New Chat" (active stream) ──────────────

describe('Bug Condition — Chat data loss on "New Chat" (active stream)', () => {
  /**
   * **Validates: Requirements 2.2**
   *
   * EXPECTED behavior: When user clicks "New Chat" during an active stream,
   * the stream should be aborted and state cleared immediately WITHOUT
   * calling getHistory (since backend may not have persisted yet).
   *
   * On UNFIXED code this partially works (abort fires) but the test encodes
   * the full expected branching: abort + clear without verification.
   * This test should PASS on unfixed code since the abort-and-clear behavior
   * already exists — it validates the stream abort path is preserved.
   */
  it('aborts stream and clears state immediately without getHistory call', async () => {
    // Create a stream that never completes (simulates active streaming)
    let streamAborted = false;
    mockSendMessageStream.mockImplementation(async function* (_sid: string, _msg: string, _ctx: unknown, signal?: AbortSignal) {
      yield { type: 'token', content: 'Partial response...' };
      // Wait until aborted
      await new Promise<void>((_, reject) => {
        if (signal?.aborted) {
          streamAborted = true;
          reject(new DOMException('Aborted', 'AbortError'));
          return;
        }
        signal?.addEventListener('abort', () => {
          streamAborted = true;
          reject(new DOMException('Aborted', 'AbortError'));
        });
      });
    });

    const { default: ChatPage } = await import('../page');
    render(<ChatPage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Patient has fever' } });

    // Start sending — this will begin streaming
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    // Wait for partial streaming content to appear
    await waitFor(() => {
      expect(screen.getByText('Patient has fever')).toBeDefined();
    });

    // Reset getHistory mock call count to track only post-click calls
    mockGetHistory.mockClear();

    // Click "New Chat" while stream is active
    const newChatBtn = screen.getByRole('button', { name: /newSession/i });
    await act(async () => {
      fireEvent.click(newChatBtn);
    });

    // EXPECTED: stream was aborted
    await waitFor(() => {
      expect(streamAborted).toBe(true);
    });

    // EXPECTED: getHistory was NOT called (skip verification during active stream)
    expect(mockGetHistory).not.toHaveBeenCalled();

    // EXPECTED: messages are cleared after abort
    await waitFor(() => {
      expect(screen.queryByText('Patient has fever')).toBeNull();
    });
  });
});
