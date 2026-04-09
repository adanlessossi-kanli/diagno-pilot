/**
 * Page-level tests for ChatPage
 * Validates: Requirements 7.8
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import React from 'react';
import type { StreamEvent } from '@diagno-pilot/api-client';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockSendMessageStream = vi.fn();

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
      getHistory: vi.fn().mockResolvedValue(null),
    },
    patients: {
      listAllPatients: vi.fn().mockResolvedValue([]),
    },
  }),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

function mockStreamFromEvents(events: StreamEvent[]) {
  return async function* () {
    for (const event of events) {
      yield event;
    }
  };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ChatPage — page-level tests', () => {
  it('renders the message input textarea', async () => {
    const { default: ChatPage } = await import('../page');
    render(<ChatPage />);

    // The textarea has aria-label from t('placeholder') which returns 'placeholder'
    expect(screen.getByRole('textbox')).toBeDefined();
  });

  it('renders the send button', async () => {
    const { default: ChatPage } = await import('../page');
    render(<ChatPage />);

    expect(screen.getByRole('button', { name: /send/i })).toBeDefined();
  });

  it('appends user message to conversation after sending', async () => {
    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        { type: 'token', content: 'Based on the symptoms, I recommend...' },
        {
          type: 'done',
          answer: 'Based on the symptoms, I recommend...',
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
    fireEvent.change(textarea, { target: { value: 'Patient has fever and cough' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    // User message should appear immediately (optimistic update)
    expect(screen.getByText('Patient has fever and cough')).toBeDefined();
  });

  it('renders assistant response after sending a message', async () => {
    const assistantContent = 'Based on the symptoms, I recommend rest and hydration.';
    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        { type: 'token', content: assistantContent },
        {
          type: 'done',
          answer: assistantContent,
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
    fireEvent.change(textarea, { target: { value: 'Patient has fever and cough' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(assistantContent)).toBeDefined();
    });
  });

  it('renders source citations when assistant response includes sources', async () => {
    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        { type: 'token', content: 'Here is the answer with sources.' },
        {
          type: 'done',
          answer: 'Here is the answer with sources.',
          session_id: 'sess-1',
          sources: [
            {
              document_id: 'doc-1',
              title: 'WHO Guidelines 2024',
              source: 'who.int',
              section: 'Chapter 3',
              excerpt: 'Fever management protocol',
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
    fireEvent.change(textarea, { target: { value: 'What is the treatment for fever?' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    await waitFor(() => {
      expect(screen.getByText('Here is the answer with sources.')).toBeDefined();
    });

    // Sources toggle button should be visible (shows count)
    await waitFor(() => {
      // SourcesPanel renders a button with text "sources (1)"
      const sourcesBtn = screen.getByRole('button', { name: /sources/i });
      expect(sourcesBtn).toBeDefined();
    });
  });

  it('calls the chat API with the message content', async () => {
    mockSendMessageStream.mockImplementation(
      mockStreamFromEvents([
        { type: 'token', content: 'Response' },
        {
          type: 'done',
          answer: 'Response',
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
    fireEvent.change(textarea, { target: { value: 'What are the symptoms of malaria?' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    await waitFor(() => {
      expect(mockSendMessageStream).toHaveBeenCalledOnce();
    });

    const [, messageContent] = mockSendMessageStream.mock.calls[0] as [string, string];
    expect(messageContent).toBe('What are the symptoms of malaria?');
  });
});
