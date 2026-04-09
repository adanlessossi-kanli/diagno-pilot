/**
 * Bug condition exploration test — Silent Stream Interruption Shows No Indicator
 *
 * Property 1: Bug Condition — When the SSE stream ends without emitting a `done`
 * or `error` event (connection drop, network timeout, server crash) after tokens
 * have been received, the assistant message SHOULD end with an interruption
 * indicator and have `interrupted === true`.
 *
 * **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists.
 * **DO NOT attempt to fix the test or the code when it fails.**
 *
 * Validates: Requirements 1.1, 1.2, 2.1
 *
 * Counterexamples found (documented after running on unfixed code):
 *   - tokens=[" "] → message content is " " with no "[Response interrupted]"
 *     indicator (shrunk minimal counterexample from fast-check)
 *   - tokens=["Hello", " world"] → message content is "Hello world" with no
 *     "[Response interrupted]" indicator appended
 *   - The `interrupted` flag is undefined on all assistant messages
 *   The property fails for ALL token sequences — the bug is universal.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import fc from 'fast-check';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import React from 'react';

// ─── Mocks (must be before imports that use them) ─────────────────────────────

// Mock next-intl
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

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => ({ locale: 'en' }),
}));

// Mock AuthContext
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

/**
 * Creates a mock async generator that yields token events for each string
 * in `tokens`, then returns (no `done`, no `error`) — simulating a stream
 * interruption (connection drop / server crash).
 */
async function* interruptedStream(
  tokens: string[],
): AsyncGenerator<import('@diagno-pilot/api-client').StreamEvent> {
  for (const content of tokens) {
    yield { type: 'token', content };
  }
  // Stream ends here — no `done`, no `error`
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  // jsdom doesn't implement scrollIntoView
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
  vi.restoreAllMocks();
});

// ─── Import component under test (after mocks) ───────────────────────────────

import ChatPage from '../app/[locale]/chat/page';

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('Property 1: Bug Condition — Silent Stream Interruption Shows No Indicator', () => {
  /**
   * Property-based test: For any non-empty sequence of non-empty tokens, when
   * the stream ends without a `done` or `error` event (simulating connection
   * drop), the final assistant message content MUST end with
   * "\n\n[Response interrupted]" and the message MUST have `interrupted === true`.
   *
   * EXPECTED TO FAIL on unfixed code — the assistant message will contain only
   * the concatenated tokens with no interruption indicator.
   */
  it('interrupted stream appends indicator to assistant message (PBT)', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(fc.string({ minLength: 1 }), { minLength: 1, maxLength: 20 }),
        async (tokens) => {
          // Clean up previous renders to avoid DOM pollution between iterations
          cleanup();
          vi.clearAllMocks();
          localStorage.clear();

          // Set up the mock stream that yields tokens then returns (interrupted)
          mockStreamGenerator = interruptedStream(tokens);

          const { container, unmount } = render(<ChatPage />);

          // Type a message into the textarea (scoped to this render's container)
          const textarea = container.querySelector('textarea')!;
          fireEvent.change(textarea, { target: { value: 'Test question' } });

          // Click send (find the send button within this container)
          const sendButton = container.querySelector('button[aria-label="Send"]')!;
          fireEvent.click(sendButton);

          // Wait for streaming to complete (the for-await loop exits)
          const expectedContent = tokens.join('');
          await waitFor(
            () => {
              const assistantBubbles = container.querySelectorAll('.rounded-bl-sm');
              const lastBubble = assistantBubbles[assistantBubbles.length - 1];
              expect(lastBubble).toBeTruthy();
              expect(lastBubble!.textContent).toContain(expectedContent);
            },
            { timeout: 3000 },
          );

          // Now assert the expected behavior:
          const assistantBubbles = container.querySelectorAll('.rounded-bl-sm');
          const lastBubble = assistantBubbles[assistantBubbles.length - 1];

          // BUG: On unfixed code, the content is just the concatenated tokens
          // with no interruption indicator appended.
          // Expected: content ends with "[Response interrupted]"
          expect(lastBubble!.textContent).toContain('[Response interrupted]');

          unmount();
          return true;
        },
      ),
      { numRuns: 5 },
    );
  });

  /**
   * Concrete example: stream yields ["Hello", " world"] then returns.
   * Expected: message ends with "\n\n[Response interrupted]"
   * On unfixed code: message is just "Hello world" with no indicator.
   */
  it('concrete example: ["Hello", " world"] → should show interruption indicator', async () => {
    mockStreamGenerator = interruptedStream(['Hello', ' world']);

    render(<ChatPage />);

    // Type a message and send
    const textarea = screen.getByPlaceholderText(mockTranslations.placeholder);
    fireEvent.change(textarea, { target: { value: 'What is malaria?' } });

    const sendButton = screen.getByRole('button', { name: mockTranslations.send });
    fireEvent.click(sendButton);

    // Wait for the assistant message to appear with token content
    await waitFor(
      () => {
        const bubbles = document.querySelectorAll('.rounded-bl-sm');
        const last = bubbles[bubbles.length - 1];
        expect(last).toBeTruthy();
        expect(last!.textContent).toContain('Hello world');
      },
      { timeout: 3000 },
    );

    // Assert expected behavior (will FAIL on unfixed code)
    const bubbles = document.querySelectorAll('.rounded-bl-sm');
    const last = bubbles[bubbles.length - 1];

    // BUG: content is "Hello world" — no interruption indicator
    // Expected: content ends with "[Response interrupted]"
    expect(last!.textContent).toContain('[Response interrupted]');
  });
});
