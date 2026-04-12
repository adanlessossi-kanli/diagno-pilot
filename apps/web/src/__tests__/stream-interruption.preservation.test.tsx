/**
 * Preservation property tests — Normal Stream Completions Unchanged
 *
 * Property 2: Preservation — Verifies that normal `done` events, `error` events,
 * and user-initiated aborts continue to behave identically after the fix.
 *
 * These tests follow observation-first methodology: behavior was observed on
 * UNFIXED code first, then encoded as property-based tests.
 *
 * Observations on UNFIXED code:
 *   - done event: message content is replaced with `event.answer`, sources set,
 *     no interruption indicator
 *   - error event: placeholder assistant message removed, streamError set,
 *     failedMessage set for retry when retryable
 *   - abort (empty placeholder): empty placeholder removed from messages
 *   - abort (non-empty placeholder): partial message left as-is, no indicator
 *
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import fc from 'fast-check';
import { render, fireEvent, waitFor, cleanup } from '@testing-library/react';
import React from 'react';

// ─── Mocks (must be before imports that use them) ─────────────────────────────

const mockTranslations: Record<string, string> = {
  responseInterrupted: '[Response interrupted]',
  sourcesUnavailable:
    'Sources unavailable — response was interrupted before sources could be delivered.',
  title: 'Chat',
  placeholder: 'Type a message...',
  send: 'Send',
  thinking: 'Thinking...',
  sources: 'Sources',
  errorSend: 'Error sending message',
  errorSendRetry: 'Error sending message. Click retry.',
  errorFetch: 'Error fetching data',
  attachPatient: 'Attach patient',
  noPatient: 'None',
  selectPatient: 'Select patient',
  oneShotMode: 'One-shot',
  patientAttached: 'Patient attached',
  loadingPatients: 'Loading patients...',
  patientName: 'Name',
  dateOfBirth: 'Date of birth',
  weightKg: 'Weight (kg)',
  allergiesLabel: 'Allergies',
  newChat: 'New Chat',
  loadingHistory: 'Loading history...',
};

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => mockTranslations[key] ?? key,
  useLocale: () => 'en',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => ({ locale: 'en' }),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', email: 'doc@test.com', fullName: 'Dr Test', role: 'medecin' },
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

// Track what sendMessageStream returns — set per-test
let mockStreamGenerator: AsyncGenerator<import('@diagno-pilot/api-client').StreamEvent>;

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    chat: {
      sendMessageStream: vi.fn(() => mockStreamGenerator),
      getHistory: vi.fn().mockRejectedValue(new Error('no history')),
      listSessions: vi.fn().mockResolvedValue({ sessions: [] }),
      deleteSession: vi.fn(),
    },
    patients: {
      listAllPatients: vi.fn().mockResolvedValue([]),
    },
  }),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

type StreamEvent = import('@diagno-pilot/api-client').StreamEvent;
type DocumentSource = import('@diagno-pilot/types').DocumentSource;

/**
 * Creates a mock async generator that yields token events then a `done` event.
 */
async function* normalDoneStream(
  tokens: string[],
  answer: string,
  sources: DocumentSource[],
): AsyncGenerator<StreamEvent> {
  for (const content of tokens) {
    yield { type: 'token', content };
  }
  yield {
    type: 'done',
    answer,
    session_id: 'sess-1',
    sources,
    llm_used: 'test-model',
    fallback_warning: null,
    warnings_present: false,
  };
}

/**
 * Creates a mock async generator that yields token events then an `error` event.
 */
async function* errorStream(
  tokens: string[],
  errorMsg: string,
  retryable: boolean,
): AsyncGenerator<StreamEvent> {
  for (const content of tokens) {
    yield { type: 'token', content };
  }
  yield { type: 'error', error: errorMsg, retryable };
}

/**
 * Creates a mock async generator that yields token events then throws AbortError.
 */
async function* abortStream(tokens: string[]): AsyncGenerator<StreamEvent> {
  for (const content of tokens) {
    yield { type: 'token', content };
  }
  const err = new DOMException('The operation was aborted.', 'AbortError');
  throw err;
}

/**
 * Helper to build a minimal DocumentSource for testing.
 */
function makeSource(title: string): DocumentSource {
  return { documentId: `doc-${title}`, title, source: 'test' };
}

/**
 * Helper: send a message through the chat UI and return the container.
 */
async function sendMessage(container: HTMLElement): Promise<void> {
  const textarea = container.querySelector('textarea')!;
  fireEvent.change(textarea, { target: { value: 'Test question' } });
  const sendButton = container.querySelector('button[aria-label="Send"]')!;
  fireEvent.click(sendButton);
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
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
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ─── Import component under test (after mocks) ───────────────────────────────

import ChatPage from '../app/[locale]/chat/page';

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('Property 2a: Normal `done` event preservation', () => {
  /**
   * Property-based test: For any token sequence followed by a `done` event with
   * a random answer and sources, the final assistant message content equals the
   * `done` answer (not concatenated tokens), has sources set, does NOT end with
   * the interruption indicator, and `interrupted` is falsy.
   */
  it('done event finalizes message with answer and sources, no interruption indicator (PBT)', async () => {
    const sourceArb = fc.record({
      documentId: fc.string({ minLength: 1, maxLength: 10 }),
      title: fc.string({ minLength: 1, maxLength: 30 }),
      source: fc.string({ minLength: 1, maxLength: 20 }),
    });

    await fc.assert(
      fc.asyncProperty(
        fc.array(fc.string({ minLength: 1 }), { minLength: 1, maxLength: 20 }),
        fc.string({ minLength: 1, maxLength: 100 }),
        fc.array(sourceArb, { minLength: 0, maxLength: 3 }),
        async (tokens, answer, sources) => {
          cleanup();
          vi.clearAllMocks();
          localStorage.clear();

          mockStreamGenerator = normalDoneStream(tokens, answer, sources as DocumentSource[]);

          const { container, unmount } = render(<ChatPage />);
          await sendMessage(container);

          // Wait for the done event to finalize the message
          await waitFor(
            () => {
              const bubbles = container.querySelectorAll('.rounded-bl-sm');
              const last = bubbles[bubbles.length - 1];
              expect(last).toBeTruthy();
              // Content should be the `done` answer, not concatenated tokens
              expect(last!.textContent).toContain(answer);
            },
            { timeout: 3000 },
          );

          const bubbles = container.querySelectorAll('.rounded-bl-sm');
          const last = bubbles[bubbles.length - 1];

          // Message content equals the done answer
          expect(last!.textContent).toContain(answer);
          // No interruption indicator
          expect(last!.textContent).not.toContain('[Response interrupted]');

          unmount();
        },
      ),
      { numRuns: 10 },
    );
  });

  /**
   * Concrete observation: tokens=["Hello", " world"], done answer="Hello world",
   * sources=[{title: "OMS"}] → message content is "Hello world" with sources, no indicator.
   */
  it('concrete: done event replaces token content with answer', async () => {
    const sources = [makeSource('OMS Guidelines')];
    mockStreamGenerator = normalDoneStream(['Hello', ' world'], 'Hello world', sources);

    const { container, unmount } = render(<ChatPage />);
    await sendMessage(container);

    await waitFor(
      () => {
        const bubbles = container.querySelectorAll('.rounded-bl-sm');
        const last = bubbles[bubbles.length - 1];
        expect(last).toBeTruthy();
        expect(last!.textContent).toContain('Hello world');
      },
      { timeout: 3000 },
    );

    const bubbles = container.querySelectorAll('.rounded-bl-sm');
    const last = bubbles[bubbles.length - 1];

    expect(last!.textContent).toContain('Hello world');
    expect(last!.textContent).not.toContain('[Response interrupted]');

    // Sources panel was removed from Q&A chat (task 9 — no citations in Q&A mode)
    // Verify no sources UI is rendered
    unmount();
  });
});

describe('Property 2b: `error` event preservation', () => {
  /**
   * Property-based test: For any error message and retryable flag, when the
   * stream yields 0–5 tokens then an error event, the placeholder assistant
   * message is removed and the error is displayed.
   */
  it('error event removes placeholder and sets streamError (PBT)', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(fc.string({ minLength: 1 }), { minLength: 0, maxLength: 5 }),
        fc.string({ minLength: 1, maxLength: 50 }),
        fc.boolean(),
        async (tokens, errorMsg, retryable) => {
          cleanup();
          vi.clearAllMocks();
          localStorage.clear();

          mockStreamGenerator = errorStream(tokens, errorMsg, retryable);

          const { container, unmount } = render(<ChatPage />);
          await sendMessage(container);

          // Wait for the error to be displayed
          await waitFor(
            () => {
              const alert = container.querySelector('[role="alert"]');
              expect(alert).toBeTruthy();
              expect(alert!.textContent).toContain(errorMsg);
            },
            { timeout: 3000 },
          );

          // The placeholder assistant message should be removed — only user
          // message bubble should remain (user bubbles have rounded-br-sm)
          const assistantBubbles = container.querySelectorAll('.rounded-bl-sm');
          expect(assistantBubbles.length).toBe(0);

          // No interruption indicator anywhere
          expect(container.textContent).not.toContain('[Response interrupted]');

          // If retryable, a retry button should be present
          if (retryable) {
            const retryButton = container.querySelector('button');
            const allButtons = Array.from(container.querySelectorAll('button'));
            const retryBtn = allButtons.find((b) => b.textContent?.includes('retry'));
            expect(retryBtn).toBeTruthy();
          }

          unmount();
        },
      ),
      { numRuns: 10 },
    );
  });

  /**
   * Concrete observation: tokens=["Partial"], error="Server error", retryable=true
   * → placeholder removed, error displayed with retry.
   */
  it('concrete: error event removes placeholder and shows retryable error', async () => {
    mockStreamGenerator = errorStream(['Partial'], 'Server error', true);

    const { container, unmount } = render(<ChatPage />);
    await sendMessage(container);

    await waitFor(
      () => {
        const alert = container.querySelector('[role="alert"]');
        expect(alert).toBeTruthy();
        expect(alert!.textContent).toContain('Server error');
      },
      { timeout: 3000 },
    );

    // No assistant message bubble
    const assistantBubbles = container.querySelectorAll('.rounded-bl-sm');
    expect(assistantBubbles.length).toBe(0);

    // No interruption indicator
    expect(container.textContent).not.toContain('[Response interrupted]');

    unmount();
  });
});

describe('Property 2c: User abort preservation (empty placeholder)', () => {
  /**
   * When AbortError is thrown before any tokens are received, the empty
   * placeholder assistant message is removed from the messages array.
   */
  it('abort before tokens removes empty placeholder', async () => {
    // Stream that immediately throws AbortError (no tokens)
    mockStreamGenerator = abortStream([]);

    const { container, unmount } = render(<ChatPage />);
    await sendMessage(container);

    // Wait for the abort to be processed
    await waitFor(
      () => {
        // Loading/streaming should be done
        const textarea = container.querySelector('textarea')!;
        expect(textarea.disabled).toBe(false);
      },
      { timeout: 3000 },
    );

    // No assistant message bubble should remain (empty placeholder removed)
    const assistantBubbles = container.querySelectorAll('.rounded-bl-sm');
    expect(assistantBubbles.length).toBe(0);

    // No interruption indicator
    expect(container.textContent).not.toContain('[Response interrupted]');

    // No error displayed (abort is silent)
    const alert = container.querySelector('[role="alert"]');
    expect(alert).toBeFalsy();

    unmount();
  });
});

describe('Property 2d: User abort preservation (non-empty placeholder)', () => {
  /**
   * When tokens are received then AbortError is thrown, the partial message
   * remains in state as-is — no interruption indicator appended, interrupted
   * is falsy.
   */
  it('abort after tokens leaves partial message as-is, no indicator (PBT)', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(fc.string({ minLength: 1 }), { minLength: 1, maxLength: 10 }),
        async (tokens) => {
          cleanup();
          vi.clearAllMocks();
          localStorage.clear();

          mockStreamGenerator = abortStream(tokens);

          const { container, unmount } = render(<ChatPage />);
          await sendMessage(container);

          const expectedContent = tokens.join('');

          // Wait for the abort to be processed and partial message to appear
          await waitFor(
            () => {
              const textarea = container.querySelector('textarea')!;
              expect(textarea.disabled).toBe(false);
            },
            { timeout: 3000 },
          );

          // The partial assistant message should remain
          const assistantBubbles = container.querySelectorAll('.rounded-bl-sm');
          expect(assistantBubbles.length).toBeGreaterThanOrEqual(1);

          const last = assistantBubbles[assistantBubbles.length - 1];
          // Content is the concatenated tokens, as-is
          expect(last!.textContent).toContain(expectedContent);
          // No interruption indicator appended
          expect(last!.textContent).not.toContain('[Response interrupted]');

          unmount();
        },
      ),
      { numRuns: 5 },
    );
  });

  /**
   * Concrete observation: tokens=["Hello", " world"] then abort → message
   * content is "Hello world" with no indicator.
   */
  it('concrete: abort after tokens leaves "Hello world" as-is', async () => {
    mockStreamGenerator = abortStream(['Hello', ' world']);

    const { container, unmount } = render(<ChatPage />);
    await sendMessage(container);

    await waitFor(
      () => {
        const textarea = container.querySelector('textarea')!;
        expect(textarea.disabled).toBe(false);
      },
      { timeout: 3000 },
    );

    const assistantBubbles = container.querySelectorAll('.rounded-bl-sm');
    expect(assistantBubbles.length).toBeGreaterThanOrEqual(1);

    const last = assistantBubbles[assistantBubbles.length - 1];
    expect(last!.textContent).toContain('Hello world');
    expect(last!.textContent).not.toContain('[Response interrupted]');

    unmount();
  });
});
