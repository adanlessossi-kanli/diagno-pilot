/**
 * Preservation property tests — Unchanged Chat Behaviors
 *
 * These tests capture baseline behavior that MUST PASS on the current unfixed code.
 * After the fix is applied, these tests verify no regressions were introduced.
 *
 * **Validates: Requirements 3.1, 3.2, 3.4, 3.5, 3.6**
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import React from 'react';
import fc from 'fast-check';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockGetHistory = vi.fn();
const mockSendMessageStream = vi.fn();
const mockListAllPatients = vi.fn().mockResolvedValue([]);

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
    },
    patients: {
      listAllPatients: mockListAllPatients,
    },
  }),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

function mockStreamFromEvents(events: Array<{ type: string; content?: string; answer?: string; session_id?: string; sources?: unknown[]; llm_used?: string; fallback_warning?: unknown; warnings_present?: boolean; error?: string; retryable?: boolean }>) {
  return async function* () {
    for (const event of events) {
      yield event;
    }
  };
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
  mockGetHistory.mockResolvedValue(null);
});

afterEach(() => {
  cleanup();
});


// ─── Preservation: Empty Session New Chat (Req 3.1) ───────────────────────────

describe('Preservation — Empty session "New Chat" (Req 3.1)', () => {
  /**
   * **Validates: Requirements 3.1**
   *
   * Property: For all empty-state configurations, clicking "New Chat" with
   * zero messages generates a new session ID and resets state without any
   * backend call (getHistory is NOT called beyond the initial mount).
   */
  it('clicking "New Chat" with zero messages resets state without backend call', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          initialInput: fc.string({ minLength: 0, maxLength: 50 }),
        }),
        async ({ initialInput }) => {
          cleanup();
          vi.clearAllMocks();
          localStorage.clear();
          mockGetHistory.mockResolvedValue(null);

          const { default: ChatPage } = await import('../page');
          render(<ChatPage />);

          // Optionally type something in the input (but don't send)
          if (initialInput.length > 0) {
            const textarea = screen.getByRole('textbox');
            fireEvent.change(textarea, { target: { value: initialInput } });
          }

          // Record getHistory call count after mount
          await waitFor(() => {
            // Wait for mount effects to settle
          });
          const callsAfterMount = mockGetHistory.mock.calls.length;

          // Click "New Chat" with zero messages
          const newChatBtn = screen.getByRole('button', { name: /newSession/i });
          await act(async () => {
            fireEvent.click(newChatBtn);
          });

          // getHistory should NOT have been called again (no verification needed)
          expect(mockGetHistory.mock.calls.length).toBe(callsAfterMount);

          // Input should be cleared
          const textarea = screen.getByRole('textbox');
          expect((textarea as HTMLTextAreaElement).value).toBe('');

          return true;
        },
      ),
      { numRuns: 5 },
    );
  });
});

// ─── Preservation: SSE Streaming (Req 3.2, 3.4, 3.5, 3.6) ───────────────────

describe('Preservation — SSE streaming behavior (Req 3.2, 3.4, 3.5, 3.6)', () => {
  /**
   * **Validates: Requirements 3.2, 3.4**
   *
   * Tokens append to assistant message, "done" event finalizes content and sources.
   */
  it('tokens append incrementally and "done" finalizes with sources', async () => {
    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        { type: 'token', content: 'Hello' },
        { type: 'token', content: ' world' },
        {
          type: 'done',
          answer: 'Hello world',
          session_id: 'sess-1',
          sources: [
            {
              document_id: 'doc-1',
              title: 'Test Source',
              source: 'test.com',
              section: 'Section 1',
              excerpt: 'Excerpt text',
            },
          ],
          llm_used: 'test-model',
          fallback_warning: null,
          warnings_present: false,
        },
      ]),
    );

    const { default: ChatPage } = await import('../page');
    render(<ChatPage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Test message' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    // Final message should contain the full text
    await waitFor(() => {
      expect(screen.getByText('Hello world')).toBeDefined();
    });

    // User message should be present
    expect(screen.getByText('Test message')).toBeDefined();

    // Sources button should be visible
    await waitFor(() => {
      const sourcesBtn = screen.getByRole('button', { name: /sources/i });
      expect(sourcesBtn).toBeDefined();
    });

    // Streaming cursor should be gone after done
    const cursor = document.querySelector('.streaming-cursor');
    expect(cursor).toBeNull();
  });

  /**
   * **Validates: Requirements 3.5, 3.6**
   *
   * Abort on unmount cleans up placeholder; stream abort fires correctly.
   */
  it('aborts stream and cleans up placeholder when "New Chat" is clicked during streaming', async () => {
    let streamAborted = false;
    mockSendMessageStream.mockImplementation(
      async function* (_sid: string, _msg: string, _ctx: unknown, signal?: AbortSignal) {
        yield { type: 'token', content: 'Partial response' };
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
      },
    );

    const { default: ChatPage } = await import('../page');
    render(<ChatPage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Abort test' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    // Wait for partial content
    await waitFor(() => {
      expect(screen.getByText('Abort test')).toBeDefined();
    });

    // Click "New Chat" to abort
    const newChatBtn = screen.getByRole('button', { name: /newSession/i });
    await act(async () => {
      fireEvent.click(newChatBtn);
    });

    // Stream should have been aborted
    await waitFor(() => {
      expect(streamAborted).toBe(true);
    });

    // Messages should be cleared after abort
    await waitFor(() => {
      expect(screen.queryByText('Abort test')).toBeNull();
    });
  });
});


// ─── Preservation: Session Restore (Req 3.4) ─────────────────────────────────

describe('Preservation — Session restore from localStorage (Req 3.4)', () => {
  /**
   * **Validates: Requirements 3.4**
   *
   * Loading chat page with a stored session ID in localStorage fetches
   * history via getHistory and displays messages.
   */
  it('restores session messages from backend when localStorage has a session ID', async () => {
    const storedSessionId = 'stored-session-123';
    localStorage.setItem('diagno-pilot-chat-session', storedSessionId);

    mockGetHistory.mockResolvedValueOnce({
      messages: [
        { id: 'msg-1', role: 'user', content: 'Previous question', timestamp: new Date().toISOString() },
        { id: 'msg-2', role: 'assistant', content: 'Previous answer', timestamp: new Date().toISOString() },
      ],
    });

    const { default: ChatPage } = await import('../page');
    render(<ChatPage />);

    // getHistory should be called with the stored session ID
    await waitFor(() => {
      expect(mockGetHistory).toHaveBeenCalledWith(storedSessionId);
    });

    // Restored messages should be displayed
    await waitFor(() => {
      expect(screen.getByText('Previous question')).toBeDefined();
      expect(screen.getByText('Previous answer')).toBeDefined();
    });
  });
});
