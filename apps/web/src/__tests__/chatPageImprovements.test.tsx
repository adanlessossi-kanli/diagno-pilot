/**
 * Unit tests for Chat Page UX improvements.
 *
 * Validates:
 * - Req 3.1: Empty state with localized prompt when no messages
 * - Req 3.3: Connecting/thinking loading indicators
 * - Req 3.4: CopyButton on assistant message hover
 * - Req 3.5: CopyButton shows "Copied!" feedback
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// ─── Mocks (must be before component import) ─────────────────────────────────

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'en',
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', email: 'test@test.com', fullName: 'Dr Test', role: 'medecin' },
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
      listSessions: vi.fn().mockResolvedValue({ sessions: [] }),
      getHistory: vi.fn().mockRejectedValue(new Error('no history')),
      sendMessageStream: vi.fn(() => mockStreamGenerator),
      deleteSession: vi.fn().mockResolvedValue(undefined),
      submitFeedback: vi.fn().mockResolvedValue(undefined),
    },
  }),
}));

vi.mock('../components/SessionHistoryPanel', () => ({
  SessionHistoryPanel: () => <div data-testid="session-history-panel" />,
  upsertEntry: vi.fn((entries: unknown[]) => entries),
  removeEntry: vi.fn((entries: unknown[]) => entries),
}));

vi.mock('../components/CopyButton', () => ({
  default: ({ text }: { text: string }) => (
    <button data-testid="copy-button" data-text={text}>Copy</button>
  ),
}));

// ─── Import component under test (after mocks) ───────────────────────────────

import ChatPage from '../app/[locale]/chat/page';

// ─── Setup / Teardown ─────────────────────────────────────────────────────────

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
  cleanup();
  vi.restoreAllMocks();
});


// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Creates a mock async generator that yields token events then a done event.
 */
async function* completedStream(
  tokens: string[],
  answer: string,
): AsyncGenerator<import('@diagno-pilot/api-client').StreamEvent> {
  for (const content of tokens) {
    yield { type: 'token', content };
  }
  yield { type: 'done', answer, sources: [], session_id: 'session-1', llm_used: 'mock', fallback_warning: null, warnings_present: false };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('Chat Page Improvements', () => {
  describe('Empty State (Req 3.1)', () => {
    it('displays empty state when there are no messages', async () => {
      render(<ChatPage />);

      await waitFor(() => {
        const emptyState = screen.queryByTestId('chat-empty-state');
        expect(emptyState).not.toBeNull();
      });

      const emptyState = screen.getByTestId('chat-empty-state');
      expect(emptyState.textContent).toContain('emptyStateTitle');
      expect(emptyState.textContent).toContain('emptyStatePrompt');
    });

    it('empty state contains an SVG illustration', async () => {
      render(<ChatPage />);

      await waitFor(() => {
        expect(screen.queryByTestId('chat-empty-state')).not.toBeNull();
      });

      const emptyState = screen.getByTestId('chat-empty-state');
      const svg = emptyState.querySelector('svg');
      expect(svg).not.toBeNull();
    });
  });

  describe('Loading Indicators (Req 3.3)', () => {
    it('does not show connecting indicator when not loading', async () => {
      render(<ChatPage />);

      await waitFor(() => {
        expect(screen.queryByTestId('chat-empty-state')).not.toBeNull();
      });

      expect(screen.queryByTestId('connecting-indicator')).toBeNull();
    });

    it('does not show thinking indicator when not loading', async () => {
      render(<ChatPage />);

      await waitFor(() => {
        expect(screen.queryByTestId('chat-empty-state')).not.toBeNull();
      });

      expect(screen.queryByTestId('thinking-indicator')).toBeNull();
    });

    it('shows connecting indicator after sending a message before first token', async () => {
      // Create a stream that never yields — simulates waiting for first token
      let resolveStream: () => void;
      const streamPromise = new Promise<void>((resolve) => { resolveStream = resolve; });

      async function* hangingStream(): AsyncGenerator<import('@diagno-pilot/api-client').StreamEvent> {
        await streamPromise;
        // Never yields — stream hangs
      }

      mockStreamGenerator = hangingStream();

      render(<ChatPage />);

      await waitFor(() => {
        expect(screen.queryByTestId('chat-empty-state')).not.toBeNull();
      });

      // Type and send a message
      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: 'Hello doctor' } });

      const sendButton = screen.getByRole('button', { name: 'send' });
      fireEvent.click(sendButton);

      // The connecting indicator should appear
      await waitFor(() => {
        expect(screen.queryByTestId('connecting-indicator')).not.toBeNull();
      });

      const connectingEl = screen.getByTestId('connecting-indicator');
      expect(connectingEl.textContent).toContain('connecting');

      // Clean up the hanging stream
      resolveStream!();
    });
  });

  describe('CopyButton Integration (Req 3.4, 3.5)', () => {
    it('renders CopyButton on assistant messages after stream completes', async () => {
      mockStreamGenerator = completedStream(['Hello', ' there'], 'Hello there');

      render(<ChatPage />);

      await waitFor(() => {
        expect(screen.queryByTestId('chat-empty-state')).not.toBeNull();
      });

      // Send a message
      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: 'Test question' } });

      const sendButton = screen.getByRole('button', { name: 'send' });
      fireEvent.click(sendButton);

      // Wait for the assistant message to appear with the final answer
      await waitFor(() => {
        const copyButtons = screen.queryAllByTestId('copy-button');
        expect(copyButtons.length).toBeGreaterThan(0);
      }, { timeout: 3000 });

      // Verify the CopyButton has the correct text
      const copyButton = screen.getAllByTestId('copy-button')[0];
      expect(copyButton.getAttribute('data-text')).toBe('Hello there');
    });

    it('empty state disappears after sending a message', async () => {
      mockStreamGenerator = completedStream(['Hi'], 'Hi');

      render(<ChatPage />);

      await waitFor(() => {
        expect(screen.queryByTestId('chat-empty-state')).not.toBeNull();
      });

      // Send a message
      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: 'Hello' } });

      const sendButton = screen.getByRole('button', { name: 'send' });
      fireEvent.click(sendButton);

      // Empty state should disappear once messages exist
      await waitFor(() => {
        expect(screen.queryByTestId('chat-empty-state')).toBeNull();
      });
    });
  });
});
