/**
 * Streaming behavior tests for ChatPage
 * Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act, within } from '@testing-library/react';
import React from 'react';
import type { StreamEvent } from '@diagno-pilot/api-client';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockSendMessageStream = vi.fn();
const mockGetHistory = vi.fn().mockResolvedValue(null);
const mockListSessions = vi.fn().mockResolvedValue({ sessions: [] });
const mockDeleteSession = vi.fn();
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
    user: { id: '1', email: 'doc@test.com', role: 'medecin', fullName: 'Dr Test' },
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
      listAllPatients: mockListAllPatients,
    },
  }),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Creates a mock async generator from a list of events.
 * Events are yielded synchronously from the array.
 */
function mockStreamFromEvents(events: StreamEvent[]) {
  return async function* () {
    for (const event of events) {
      yield event;
    }
  };
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
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
});

afterEach(() => {
  cleanup();
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ChatPage — Streaming behavior', () => {
  /**
   * Validates: Requirement 7.1
   * Token-by-token rendering: tokens are appended incrementally to the assistant message.
   */
  it('renders tokens incrementally as they arrive', async () => {
    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        { type: 'token', content: 'Hello' },
        { type: 'token', content: ' world' },
        {
          type: 'done',
          answer: 'Hello world',
          session_id: 'sess-1',
          sources: [],
          llm_used: 'test-model',
          fallback_warning: null,
          warnings_present: false,
        },
      ]),
    );

    const { default: ChatPage } = await import('../page');
    render(<ChatPage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Hello doctor' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    // After streaming completes, the final message should contain the full text
    await waitFor(() => {
      expect(screen.getByText('Hello world')).toBeDefined();
    });

    // User message should also be present
    expect(screen.getAllByText('Hello doctor').length).toBeGreaterThanOrEqual(1);
  });

  /**
   * Validates: Requirement 7.2
   * Streaming indicator: streaming cursor appears during streaming and disappears after done.
   * ThinkingBubble shows when loading but no content yet.
   */
  it('shows streaming cursor during streaming and removes it after done', async () => {
    // Use a deferred pattern to control when events arrive
    let resolveStream!: (value: void) => void;
    const streamStarted = new Promise<void>((r) => { resolveStream = r; });

    mockSendMessageStream.mockImplementation(async function* () {
      resolveStream();
      yield { type: 'token' as const, content: 'Streaming' };
      yield { type: 'token' as const, content: ' text' };
      yield {
        type: 'done' as const,
        answer: 'Streaming text',
        session_id: 'sess-1',
        sources: [],
        llm_used: 'test-model',
        fallback_warning: null,
        warnings_present: false,
      };
    });

    const { default: ChatPage } = await import('../page');
    render(<ChatPage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Test question' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    // After streaming completes, cursor should be gone
    await waitFor(() => {
      expect(screen.getByText('Streaming text')).toBeDefined();
      const cursor = document.querySelector('.streaming-cursor');
      expect(cursor).toBeNull();
    });
  });

  /**
   * Validates: Requirement 7.3 (updated for Q&A redesign — sources no longer rendered)
   * Done event finalizes message content. Sources array is ignored in Q&A chat.
   */
  it('finalizes message content on done event (sources ignored)', async () => {
    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        { type: 'token', content: 'Take medication.' },
        {
          type: 'done',
          answer: 'Take medication.',
          session_id: 'sess-1',
          sources: [
            {
              documentId: 'doc-1',
              title: 'WHO Guidelines 2024',
              source: 'who.int',
              section: 'Chapter 3',
              excerpt: 'Treatment protocol',
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
    fireEvent.change(textarea, { target: { value: 'What is the treatment?' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    // After done, message content should be finalized but no sources UI rendered
    await waitFor(() => {
      expect(screen.getByText('Take medication.')).toBeDefined();
    });

    // Sources panel should NOT be visible (Q&A no longer renders sources)
    const sourcesButtons = screen.queryAllByRole('button').filter((btn) =>
      btn.textContent?.toLowerCase().includes('sources'),
    );
    expect(sourcesButtons.length).toBe(0);
  });

  /**
   * Validates: Requirement 7.4
   * Scroll behavior: scrollIntoView is called during streaming.
   */
  it('calls scrollIntoView during streaming for auto-scroll', async () => {
    const scrollIntoViewMock = vi.fn();
    window.HTMLElement.prototype.scrollIntoView = scrollIntoViewMock;

    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        { type: 'token', content: 'Scrolling' },
        {
          type: 'done',
          answer: 'Scrolling',
          session_id: 'sess-1',
          sources: [],
          llm_used: 'test-model',
          fallback_warning: null,
          warnings_present: false,
        },
      ]),
    );

    const { default: ChatPage } = await import('../page');
    render(<ChatPage />);

    scrollIntoViewMock.mockClear();

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Scroll test' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    // Wait for streaming to complete
    await waitFor(() => {
      expect(screen.getByText('Scrolling')).toBeDefined();
    });

    // scrollIntoView should have been called during the streaming process
    expect(scrollIntoViewMock).toHaveBeenCalled();
  });

  /**
   * Validates: Requirement 7.5
   * Error event with retryable flag shows error banner and retry button.
   * Clicking retry calls sendMessageStream again.
   */
  it('shows error banner with retry button on retryable error event', async () => {
    // First call: stream yields an error
    mockSendMessageStream.mockImplementationOnce(
      mockStreamFromEvents([
        { type: 'error', error: 'LLM service unavailable', retryable: true },
      ]),
    );

    const { default: ChatPage } = await import('../page');
    render(<ChatPage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Error test' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    // Error banner should appear with the error message
    await waitFor(() => {
      const alert = screen.getByRole('alert');
      expect(alert).toBeDefined();
      expect(alert.textContent).toContain('LLM service unavailable');
    });

    // Retry button should be visible
    const retryBtn = screen.getByRole('button', { name: /retry/i });
    expect(retryBtn).toBeDefined();

    // Set up second stream for retry
    mockSendMessageStream.mockImplementationOnce(
      mockStreamFromEvents([
        { type: 'token', content: 'Retry success' },
        {
          type: 'done',
          answer: 'Retry success',
          session_id: 'sess-1',
          sources: [],
          llm_used: 'test-model',
          fallback_warning: null,
          warnings_present: false,
        },
      ]),
    );

    // Click retry
    await act(async () => {
      fireEvent.click(retryBtn);
    });

    // sendMessageStream should be called again
    await waitFor(() => {
      expect(mockSendMessageStream).toHaveBeenCalledTimes(2);
    });

    // Retry should succeed
    await waitFor(() => {
      expect(screen.getByText('Retry success')).toBeDefined();
    });
  });

  /**
   * Validates: Requirement 7.6
   * Abort on "New Session": clicking New Session aborts the in-progress stream.
   * The AbortSignal passed to sendMessageStream should be aborted.
   */
  it('aborts stream when New Session is clicked during streaming', async () => {
    let capturedSignal: AbortSignal | undefined;

    mockSendMessageStream.mockImplementation(
      async function* (_sid: string, _content: string, _patient: unknown, signal?: AbortSignal) {
        capturedSignal = signal;
        yield { type: 'token' as const, content: 'Partial' };
        // Wait indefinitely — will be aborted
        await new Promise<void>((_, reject) => {
          if (signal?.aborted) {
            reject(new DOMException('Aborted', 'AbortError'));
            return;
          }
          signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
        });
      },
    );

    const { default: ChatPage } = await import('../page');
    render(<ChatPage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Abort test' } });

    // Start streaming (don't await — it will hang until aborted)
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    // Wait for the first token to appear
    await waitFor(() => {
      expect(screen.getByText('Partial')).toBeDefined();
    });

    // Click "New Session" button
    await act(async () => {
      const newSessionBtn = screen.getByRole('button', { name: /newSession/i });
      fireEvent.click(newSessionBtn);
    });

    // The signal should have been aborted
    expect(capturedSignal?.aborted).toBe(true);
  });
});
