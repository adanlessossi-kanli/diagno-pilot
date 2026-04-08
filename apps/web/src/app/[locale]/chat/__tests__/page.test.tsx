/**
 * Page-level tests for ChatPage
 * Validates: Requirements 7.8
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockSendMessage = vi.fn();

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
      sendMessage: mockSendMessage,
      getHistory: vi.fn().mockResolvedValue(null),
    },
    patients: {
      listAllPatients: vi.fn().mockResolvedValue([]),
    },
  }),
}));

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
    mockSendMessage.mockResolvedValue({
      id: 'assistant-1',
      role: 'assistant',
      content: 'Based on the symptoms, I recommend...',
      timestamp: new Date().toISOString(),
      sources: [],
    });

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
    mockSendMessage.mockResolvedValue({
      id: 'assistant-1',
      role: 'assistant',
      content: assistantContent,
      timestamp: new Date().toISOString(),
      sources: [],
    });

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
    mockSendMessage.mockResolvedValue({
      id: 'assistant-1',
      role: 'assistant',
      content: 'Here is the answer with sources.',
      timestamp: new Date().toISOString(),
      sources: [
        {
          title: 'WHO Guidelines 2024',
          section: 'Chapter 3',
          excerpt: 'Fever management protocol',
        },
      ],
    });

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
    mockSendMessage.mockResolvedValue({
      id: 'assistant-1',
      role: 'assistant',
      content: 'Response',
      timestamp: new Date().toISOString(),
      sources: [],
    });

    const { default: ChatPage } = await import('../page');
    render(<ChatPage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'What are the symptoms of malaria?' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send/i }));
    });

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledOnce();
    });

    const [, messageContent] = mockSendMessage.mock.calls[0] as [string, string];
    expect(messageContent).toBe('What are the symptoms of malaria?');
  });
});
