/// <reference types="@jest/globals" />
/**
 * Screen-level tests for ChatScreen
 *
 * Feature: testing-coverage
 *
 * Unit tests:
 *  - Sending a message appends it to the conversation
 *  - Assistant reply renders with MobileSourceCitation
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react-native';
import ChatScreen from '../chat';
import type { ChatMessage } from '@diagno-pilot/types';

// ─── Mocks ────────────────────────────────────────────────────────────────────

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  useSegments: () => [],
  Link: ({ children }: { children: React.ReactNode }) => children,
}));

// ─── Mock AuthContext ─────────────────────────────────────────────────────────

const mockSendMessageStream = jest.fn();

jest.mock('../../../src/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'doc@test.com', fullName: 'Dr Test', role: 'medecin' },
    token: 'tok',
    isLoading: false,
    login: jest.fn(),
    logout: jest.fn(),
    apiClient: {
      chat: {
        sendMessageStream: mockSendMessageStream,
      },
    },
  }),
}));

jest.mock('../../../src/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'fr-TG',
    setLocale: jest.fn(),
    cacheVersion: 0,
    t: (key: string) => key,
  }),
}));

/**
 * Helper: creates an async generator that yields StreamEvent objects
 * matching the sendMessageStream contract.
 */
async function* fakeStream(reply: ChatMessage) {
  // Yield the full answer as a single 'done' event
  yield {
    type: 'done' as const,
    answer: reply.content,
    session_id: 'test-session',
    sources: reply.sources ?? [],
    llm_used: 'test-model',
    fallback_warning: null,
    warnings_present: false,
  };
}

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function makeAssistantReply(withSources = true): ChatMessage {
  return {
    id: `a-${Date.now()}`,
    role: 'assistant',
    content: 'Les fluoroquinolones sont contre-indiquées chez les enfants.',
    timestamp: new Date().toISOString(),
    sources: withSources
      ? [
          {
            documentId: 'doc-1',
            title: 'Guide antibiotiques OMS',
            source: 'oms-guidelines.pdf',
            section: 'Fluoroquinolones',
            excerpt: 'Contre-indiqué chez les moins de 18 ans.',
          },
        ]
      : [],
  };
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
});

// ─── Unit tests ───────────────────────────────────────────────────────────────

describe('ChatScreen — message sending', () => {
  it('appends user message to conversation after sending', async () => {
    mockSendMessageStream.mockReturnValue(fakeStream(makeAssistantReply(false)));

    render(<ChatScreen />);

    const input = screen.getByLabelText('Message');
    fireEvent.changeText(input, 'Quelle est la dose de ciprofloxacine ?');

    const sendButton = screen.getByLabelText('chat.send');
    await act(async () => {
      fireEvent.press(sendButton);
    });

    await waitFor(() => {
      expect(screen.getByText('Quelle est la dose de ciprofloxacine ?')).toBeTruthy();
    });
  }, 10000);

  it('renders assistant reply after sending', async () => {
    mockSendMessageStream.mockReturnValue(fakeStream(makeAssistantReply(false)));

    render(<ChatScreen />);

    const input = screen.getByLabelText('Message');
    fireEvent.changeText(input, 'Question test');

    const sendButton = screen.getByLabelText('chat.send');
    await act(async () => {
      fireEvent.press(sendButton);
    });

    await waitFor(() => {
      expect(screen.getByText('Les fluoroquinolones sont contre-indiquées chez les enfants.')).toBeTruthy();
    });
  });

  it('renders MobileSourceCitation when assistant reply has sources', async () => {
    mockSendMessageStream.mockReturnValue(fakeStream(makeAssistantReply(true)));

    render(<ChatScreen />);

    const input = screen.getByLabelText('Message');
    fireEvent.changeText(input, 'Fluoroquinolones enfants ?');

    const sendButton = screen.getByLabelText('chat.send');
    await act(async () => {
      fireEvent.press(sendButton);
    });

    await waitFor(() => {
      // MobileSourceCitation renders the source title
      expect(screen.getByText('Guide antibiotiques OMS')).toBeTruthy();
    });
  });

  it('calls sendMessage API with the typed text', async () => {
    mockSendMessageStream.mockReturnValue(fakeStream(makeAssistantReply(false)));

    render(<ChatScreen />);

    const input = screen.getByLabelText('Message');
    fireEvent.changeText(input, 'Ma question');

    const sendButton = screen.getByLabelText('chat.send');
    await act(async () => {
      fireEvent.press(sendButton);
    });

    await waitFor(() => {
      expect(mockSendMessageStream).toHaveBeenCalledWith(
        expect.any(String),
        'Ma question'
      );
    });
  });

  it('clears input after sending', async () => {
    mockSendMessageStream.mockReturnValue(fakeStream(makeAssistantReply(false)));

    render(<ChatScreen />);

    const input = screen.getByLabelText('Message');
    fireEvent.changeText(input, 'Question à envoyer');

    const sendButton = screen.getByLabelText('chat.send');
    await act(async () => {
      fireEvent.press(sendButton);
    });

    await waitFor(() => {
      expect(input.props.value).toBe('');
    });
  });
});

describe('ChatScreen — character count indicator', () => {
  it('displays 0/1000 character count on initial render', () => {
    render(<ChatScreen />);
    expect(screen.getByText('0/1000')).toBeTruthy();
  });

  it('updates character count as user types', () => {
    render(<ChatScreen />);
    const input = screen.getByLabelText('Message');
    fireEvent.changeText(input, 'Hello');
    expect(screen.getByText('5/1000')).toBeTruthy();
  });
});
