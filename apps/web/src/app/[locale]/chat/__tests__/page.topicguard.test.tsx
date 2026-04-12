/**
 * Topic Guard & Sources removal tests for ChatPage
 * Validates: Requirements 1.2, 1.3, 2.4, 13.1, 13.2, 13.5
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import React from 'react';
import type { StreamEvent } from '@diagno-pilot/api-client';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockSendMessageStream = vi.fn();
const mockGetHistory = vi.fn().mockResolvedValue(null);
const mockListSessions = vi.fn().mockResolvedValue({ sessions: [] });
const mockDeleteSession = vi.fn();
const mockListAllPatients = vi.fn().mockResolvedValue([]);
const mockSubmitFeedback = vi.fn();

window.HTMLElement.prototype.scrollIntoView = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: (ns: string) => (key: string) => `${ns}.${key}`,
  useLocale: () => 'en',
}));

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', email: 'doc@test.com', role: 'medecin', fullName: 'Dr Test' },
  }),
}));

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    chat: {
      listSessions: mockListSessions,
      getHistory: mockGetHistory,
      deleteSession: mockDeleteSession,
      sendMessageStream: mockSendMessageStream,
      submitFeedback: mockSubmitFeedback,
    },
    patients: {
      listAllPatients: mockListAllPatients,
    },
  }),
}));

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

describe('ChatPage — Sources removal (Req 1.2, 1.3)', () => {
  /**
   * Validates: Requirement 1.2
   * SourcesPanel and CitationChip are NOT rendered for assistant messages,
   * even when the done event includes a non-empty sources array.
   */
  it('does not render SourcesPanel or CitationChip for assistant messages with sources', async () => {
    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        { type: 'token', content: 'Medical answer.' },
        {
          type: 'done',
          answer: 'Medical answer.',
          session_id: 'sess-1',
          sources: [
            {
              documentId: 'doc-1',
              title: 'WHO Guidelines',
              source: 'who.int',
              section: 'Chapter 1',
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
    fireEvent.change(textarea, { target: { value: 'What is malaria?' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    await waitFor(() => {
      expect(screen.getByText('Medical answer.')).toBeDefined();
    });

    // SourcesPanel toggle button should NOT exist
    const sourcesButtons = screen.queryAllByRole('button', { name: /sources/i });
    // Filter out the send button — only look for sources-related buttons
    const sourcesPanelButtons = sourcesButtons.filter((btn) =>
      btn.textContent?.toLowerCase().includes('sources'),
    );
    expect(sourcesPanelButtons.length).toBe(0);

    // No CitationChip [N] buttons should exist
    const citationButtons = screen.queryAllByRole('button').filter((btn) =>
      /^\[\d+\]$/.test(btn.textContent?.trim() ?? ''),
    );
    expect(citationButtons.length).toBe(0);
  });

  /**
   * Validates: Requirement 1.3
   * Sources array from done SSE events is ignored — no citation UI rendered.
   */
  it('ignores sources array from done SSE events', async () => {
    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        {
          type: 'done',
          answer: 'Direct answer without citations.',
          session_id: 'sess-2',
          sources: [
            { documentId: 'd1', title: 'Doc1', source: 's1' },
            { documentId: 'd2', title: 'Doc2', source: 's2' },
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
    fireEvent.change(textarea, { target: { value: 'Test question' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    await waitFor(() => {
      expect(screen.getByText('Direct answer without citations.')).toBeDefined();
    });

    // No citation-related UI should be present
    expect(screen.queryByText(/Doc1/)).toBeNull();
    expect(screen.queryByText(/Doc2/)).toBeNull();
  });
});

describe('ChatPage — Topic Guard detection (Req 2.4, 13.1)', () => {
  /**
   * Validates: Requirement 2.4
   * [TOPIC_GUARD_REFUSAL] marker is detected and stripped from displayed text.
   */
  it('strips [TOPIC_GUARD_REFUSAL] marker from displayed assistant message', async () => {
    const refusalText = "[TOPIC_GUARD_REFUSAL]\nI'm sorry, I can only answer medical questions.";

    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        {
          type: 'done',
          answer: refusalText,
          session_id: 'sess-3',
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
    fireEvent.change(textarea, { target: { value: 'Who won the football match?' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    await waitFor(() => {
      // The stripped message should be displayed
      expect(screen.getByText("I'm sorry, I can only answer medical questions.")).toBeDefined();
    });

    // The raw marker should NOT appear in the rendered output
    expect(screen.queryByText('[TOPIC_GUARD_REFUSAL]')).toBeNull();
  });

  /**
   * Validates: Requirement 13.1
   * Feedback button appears below Topic Guard refusal messages.
   */
  it('shows feedback button below refusal messages', async () => {
    const refusalText = "[TOPIC_GUARD_REFUSAL]\nI cannot help with that topic.";

    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        {
          type: 'done',
          answer: refusalText,
          session_id: 'sess-4',
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
    fireEvent.change(textarea, { target: { value: 'Tell me about cooking' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    await waitFor(() => {
      expect(screen.getByText('I cannot help with that topic.')).toBeDefined();
    });

    // Feedback button should be present
    const feedbackBtn = screen.getByTestId('topic-guard-feedback-btn');
    expect(feedbackBtn).toBeDefined();
    expect(feedbackBtn.textContent).toBe('topicGuard.feedbackButton');
  });

  /**
   * Validates: Requirement 13.1 (negative case)
   * Feedback button does NOT appear for normal (non-refusal) assistant messages.
   */
  it('does not show feedback button for normal assistant messages', async () => {
    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        {
          type: 'done',
          answer: 'Malaria is caused by Plasmodium parasites.',
          session_id: 'sess-5',
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
    fireEvent.change(textarea, { target: { value: 'What causes malaria?' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    await waitFor(() => {
      expect(screen.getByText('Malaria is caused by Plasmodium parasites.')).toBeDefined();
    });

    // No feedback button should be present
    expect(screen.queryByTestId('topic-guard-feedback-btn')).toBeNull();
  });
});

describe('ChatPage — Feedback submission (Req 13.2, 13.5)', () => {
  /**
   * Validates: Requirement 13.2
   * Clicking feedback button calls POST /api/v1/chat/feedback with question and response.
   */
  it('calls submitFeedback API with original question and refusal response', async () => {
    const refusalText = "[TOPIC_GUARD_REFUSAL]\nSorry, I only handle medical topics.";
    mockSubmitFeedback.mockResolvedValue({ detail: 'Feedback recorded' });

    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        {
          type: 'done',
          answer: refusalText,
          session_id: 'sess-6',
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
    fireEvent.change(textarea, { target: { value: 'What is the best recipe?' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    await waitFor(() => {
      expect(screen.getByTestId('topic-guard-feedback-btn')).toBeDefined();
    });

    // Click the feedback button
    await act(async () => {
      fireEvent.click(screen.getByTestId('topic-guard-feedback-btn'));
    });

    await waitFor(() => {
      expect(mockSubmitFeedback).toHaveBeenCalledWith(
        'What is the best recipe?',
        refusalText,
      );
    });

    // Confirmation message should appear
    await waitFor(() => {
      expect(screen.getByText('topicGuard.feedbackSent')).toBeDefined();
    });
  });

  /**
   * Validates: Requirement 13.5
   * Feedback mechanism does NOT retry the question — only records feedback.
   */
  it('does not re-send the question after feedback submission', async () => {
    const refusalText = "[TOPIC_GUARD_REFUSAL]\nI cannot answer that.";
    mockSubmitFeedback.mockResolvedValue({ detail: 'Feedback recorded' });

    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        {
          type: 'done',
          answer: refusalText,
          session_id: 'sess-7',
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
    fireEvent.change(textarea, { target: { value: 'Sports question' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    await waitFor(() => {
      expect(screen.getByTestId('topic-guard-feedback-btn')).toBeDefined();
    });

    // Record how many times sendMessageStream was called before feedback
    const callsBefore = mockSendMessageStream.mock.calls.length;

    await act(async () => {
      fireEvent.click(screen.getByTestId('topic-guard-feedback-btn'));
    });

    await waitFor(() => {
      expect(mockSubmitFeedback).toHaveBeenCalledTimes(1);
    });

    // sendMessageStream should NOT have been called again
    expect(mockSendMessageStream.mock.calls.length).toBe(callsBefore);
  });

  /**
   * Validates: Requirement 13.2 (error case)
   * Shows error toast when feedback submission fails.
   */
  it('shows error message when feedback submission fails', async () => {
    const refusalText = "[TOPIC_GUARD_REFUSAL]\nNot a medical question.";
    mockSubmitFeedback.mockRejectedValue(new Error('Network error'));

    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        {
          type: 'done',
          answer: refusalText,
          session_id: 'sess-8',
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
    fireEvent.change(textarea, { target: { value: 'Politics question' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    await waitFor(() => {
      expect(screen.getByTestId('topic-guard-feedback-btn')).toBeDefined();
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('topic-guard-feedback-btn'));
    });

    // Error message should appear
    await waitFor(() => {
      expect(screen.getByText('topicGuard.feedbackError')).toBeDefined();
    });

    // Feedback button should still be visible (not replaced by success message)
    expect(screen.getByTestId('topic-guard-feedback-btn')).toBeDefined();
  });
});
