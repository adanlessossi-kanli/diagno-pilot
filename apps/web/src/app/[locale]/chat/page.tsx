'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { createApiClient } from '@diagno-pilot/api-client';
import type { StreamEvent } from '@diagno-pilot/api-client';
import type { ChatMessage } from '@diagno-pilot/types';
import { useAuth } from '../../../contexts/AuthContext';
import { SessionHistoryPanel, upsertEntry, removeEntry } from '../../../components/SessionHistoryPanel';
import type { SessionEntry } from '../../../components/SessionHistoryPanel';
import CopyButton from '../../../components/CopyButton';

// ─── Types ────────────────────────────────────────────────────────────────────

type LocalChatMessage = ChatMessage & { interrupted?: boolean };

// ─── Constants ────────────────────────────────────────────────────────────────

const SESSION_STORAGE_KEY = 'diagno-pilot-chat-session';
const TOPIC_GUARD_MARKER = '[TOPIC_GUARD_REFUSAL]';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function generateSessionId(): string {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function getStoredSessionId(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(SESSION_STORAGE_KEY);
}

function storeSessionId(id: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(SESSION_STORAGE_KEY, id);
}

function clearStoredSessionId(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(SESSION_STORAGE_KEY);
}

function isRetryableError(err: unknown): boolean {
  const status = (err as { status?: number })?.status;
  if (status === 500) return true;
  if (err instanceof Error && err.name === 'AbortError') return true;
  if (err instanceof TypeError && String(err.message).toLowerCase().includes('fetch')) return true;
  return false;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

/**
 * Strips the [TOPIC_GUARD_REFUSAL] marker from content and returns
 * whether the message is a Topic Guard refusal.
 */
function parseTopicGuardRefusal(content: string): { isRefusal: boolean; displayContent: string } {
  if (content.startsWith(TOPIC_GUARD_MARKER)) {
    const stripped = content.slice(TOPIC_GUARD_MARKER.length).replace(/^\n/, '');
    return { isRefusal: true, displayContent: stripped };
  }
  return { isRefusal: false, displayContent: content };
}

function FeedbackButton({
  question,
  response,
  apiClient,
}: {
  question: string;
  response: string;
  apiClient: ReturnType<typeof createApiClient>;
}) {
  const tGuard = useTranslations('topicGuard');
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);
  const [feedbackError, setFeedbackError] = useState(false);

  async function handleFeedback() {
    if (sent || sending) return;
    setSending(true);
    setFeedbackError(false);
    try {
      await apiClient.chat.submitFeedback(question, response);
      setSent(true);
    } catch {
      setFeedbackError(true);
    } finally {
      setSending(false);
    }
  }

  if (sent) {
    return <p className="text-xs text-green-600 mt-1 px-1">{tGuard('feedbackSent')}</p>;
  }

  return (
    <div className="mt-1 px-1">
      <button
        type="button"
        onClick={() => void handleFeedback()}
        disabled={sending}
        className="text-xs text-orange-600 hover:text-orange-800 hover:underline disabled:opacity-50"
        data-testid="topic-guard-feedback-btn"
      >
        {sending ? '…' : tGuard('feedbackButton')}
      </button>
      {feedbackError && (
        <p className="text-xs text-red-500 mt-0.5">{tGuard('feedbackError')}</p>
      )}
    </div>
  );
}

function MessageBubble({
  message,
  isStreaming,
  previousUserMessage,
  apiClient,
}: {
  message: LocalChatMessage;
  isStreaming?: boolean;
  previousUserMessage?: string;
  apiClient: ReturnType<typeof createApiClient>;
}) {
  const isUser = message.role === 'user';

  const { isRefusal, displayContent } = isUser
    ? { isRefusal: false, displayContent: message.content }
    : parseTopicGuardRefusal(message.content);

  return (
    <div className={`group relative flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[80%] ${isUser ? 'order-2' : 'order-1'}`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap ${
            isUser
              ? 'bg-blue-600 text-white rounded-br-sm'
              : 'bg-white border border-gray-200 text-gray-900 rounded-bl-sm'
          }`}
        >
          {displayContent}
          {isStreaming && (
            <span
              className="streaming-cursor"
              aria-hidden="true"
            />
          )}
        </div>
        {!isUser && isRefusal && previousUserMessage && (
          <FeedbackButton
            question={previousUserMessage}
            response={message.content}
            apiClient={apiClient}
          />
        )}
        <p className={`text-xs text-gray-400 mt-1 px-1 ${isUser ? 'text-right' : 'text-left'}`}>
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
      {!isUser && (
        <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <CopyButton text={displayContent} />
        </div>
      )}
    </div>
  );
}

function BouncingDots() {
  return (
    <span className="inline-flex gap-0.5 ml-2">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}

function ConnectingBubble() {
  const t = useTranslations('chat');
  return (
    <div className="flex justify-start" data-testid="connecting-indicator">
      <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-2.5">
        <span className="text-xs text-gray-500 italic">{t('connecting')}</span>
        <BouncingDots />
      </div>
    </div>
  );
}

function ThinkingBubble() {
  const t = useTranslations('chat');
  return (
    <div className="flex justify-start" data-testid="thinking-indicator">
      <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-2.5">
        <span className="text-xs text-gray-500 italic">{t('thinking')}</span>
        <BouncingDots />
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const t = useTranslations('chat');
  const tHistory = useTranslations('sessionHistory');
  const locale = useLocale();
  const { user } = useAuth();

  const apiClient = useMemo(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
    return createApiClient(baseUrl, undefined, () => locale);
  }, [locale]);

  // Session — restore from localStorage or generate new
  // The ID is only persisted to localStorage when the first message is sent,
  // so the mount effect won't try to fetch history for a brand-new session.
  const [sessionId, setSessionId] = useState<string>(() => {
    return getStoredSessionId() ?? generateSessionId();
  });

  // Messages
  const [messages, setMessages] = useState<LocalChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [receivedFirstToken, setReceivedFirstToken] = useState(false);
  const [error, setError] = useState('');
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Retry state: stores the failed message content for retry capability
  const [failedMessage, setFailedMessage] = useState<string | null>(null);
  // Verification state: tracks when backend verification is in flight for "New Chat"
  const [verifying, setVerifying] = useState(false);
  // Stream error with retryable flag
  const [streamError, setStreamError] = useState<{ message: string; retryable: boolean } | null>(null);

  // AbortController ref for cancelling in-progress streams
  const abortControllerRef = useRef<AbortController | null>(null);

  // Abort in-progress stream on unmount (navigation away) — Req 7.6
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  // ─── Session history state ──────────────────────────────────────────────────
  const [sessions, setSessions] = useState<SessionEntry[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [sessionsHasMore, setSessionsHasMore] = useState(true);
  const sessionsPageRef = useRef(0);
  const [sessionsLoadingMore, setSessionsLoadingMore] = useState(false);
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [announceMessage, setAnnounceMessage] = useState<string | null>(null);

  // Auto-scroll refs
  const bottomRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);

  // ─── Fetch sessions on mount (6.1) ──────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setSessionsLoading(true);
    setSessionsError(null);
    apiClient.chat.listSessions(0, 20)
      .then((res) => {
        if (cancelled) return;
        const mapped = res.sessions.map((s) => ({
          id: s.sessionId,
          preview: s.preview ?? '\u2014',
          date: s.updatedAt ?? s.createdAt ?? '',
        }));
        setSessions(mapped);
        setSessionsHasMore(res.sessions.length >= 20);
        sessionsPageRef.current = 20;
      })
      .catch(() => {
        if (!cancelled) setSessionsError(tHistory('errorFetch'));
      })
      .finally(() => {
        if (!cancelled) setSessionsLoading(false);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Load more sessions (6.1) ───────────────────────────────────────────────
  const handleLoadMore = useCallback(async () => {
    if (sessionsLoadingMore || !sessionsHasMore) return;
    setSessionsLoadingMore(true);
    try {
      const res = await apiClient.chat.listSessions(sessionsPageRef.current, 20);
      const mapped = res.sessions.map((s) => ({
        id: s.sessionId,
        preview: s.preview ?? '\u2014',
        date: s.updatedAt ?? s.createdAt ?? '',
      }));
      setSessions((prev) => {
        const existingIds = new Set(prev.map((e) => e.id));
        const deduped = mapped.filter((e) => !existingIds.has(e.id));
        return [...prev, ...deduped];
      });
      setSessionsHasMore(res.sessions.length >= 20);
      sessionsPageRef.current += 20;
    } catch {
      // Silently fail on load-more — user can scroll again
    } finally {
      setSessionsLoadingMore(false);
    }
  }, [sessionsLoadingMore, sessionsHasMore, apiClient]);

  // ─── Session select handler (6.2) ───────────────────────────────────────────
  const handleSessionSelect = useCallback(async (id: string) => {
    setOperationError(null);
    setSelectingId(id);
    try {
      const session = await apiClient.chat.getHistory(id);
      setMessages(session?.messages ?? []);
      setSessionId(id);
      storeSessionId(id);
      setAnnounceMessage(tHistory('sessionLoaded'));
    } catch {
      setOperationError(tHistory('errorLoad'));
    } finally {
      setSelectingId(null);
    }
  }, [apiClient, tHistory]);

  // ─── Session delete handler (6.3) ───────────────────────────────────────────
  const handleSessionDelete = useCallback(async (id: string) => {
    setOperationError(null);
    const snapshot = sessions;
    setSessions((prev) => removeEntry(prev, id));
    try {
      await apiClient.chat.deleteSession(id);
      setAnnounceMessage(tHistory('sessionDeleted'));
      // If deleted session is the active one, clear chat and start new session
      if (id === sessionId) {
        clearStoredSessionId();
        const newId = generateSessionId();
        setSessionId(newId);
        setMessages([]);
      }
    } catch {
      // Restore snapshot on error
      setSessions(snapshot);
      setOperationError(tHistory('errorDelete'));
    }
  }, [sessions, apiClient, tHistory, sessionId]);

  // Load message history when restoring a session from localStorage (Req 8.4)
  useEffect(() => {
    const stored = getStoredSessionId();
    if (!stored) return;
    let cancelled = false;
    setLoadingHistory(true);
    apiClient.chat.getHistory(stored)
      .then((session) => {
        if (!cancelled && session?.messages) {
          setMessages(session.messages);
        }
      })
      .catch(() => {
        // Session may have expired or been deleted — start fresh
        if (!cancelled) {
          clearStoredSessionId();
          setSessionId(generateSessionId());
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Smart auto-scroll: scroll to bottom unless user has scrolled up
  const handleMessagesScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    const threshold = 50;
    const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight <= threshold;
    userScrolledUpRef.current = !isAtBottom;
  }, []);

  useEffect(() => {
    if (!userScrolledUpRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loading, streaming]);

  // Send message
  async function handleSend(retryContent?: string) {
    const content = retryContent ?? input.trim();
    if (!content || loading || streaming) return;

    setError('');
    setStreamError(null);
    setFailedMessage(null);
    setReceivedFirstToken(false);
    if (!retryContent) setInput('');

    // Persist sessionId to localStorage on first message (Req 8.1)
    storeSessionId(sessionId);

    // Optimistically add user message
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };

    // Create a placeholder assistant message for streaming into
    const assistantMsgId = `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const placeholderAssistantMsg: ChatMessage = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg, placeholderAssistantMsg]);
    setLoading(true);
    setStreaming(true);
    userScrolledUpRef.current = false;

    // Create an AbortController for this send
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const stream = apiClient.chat.sendMessageStream(sessionId, content, undefined, controller.signal);

      let receivedDone = false;

      for await (const event of stream) {
        if (event.type === 'token') {
          setReceivedFirstToken(true);
          // Append token content to the streaming assistant message
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? { ...m, content: m.content + event.content }
                : m,
            ),
          );
        } else if (event.type === 'done') {
          // Finalize the message with full answer, sources, remove streaming state
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    content: event.answer,
                    sources: event.sources,
                  }
                : m,
            ),
          );
          // Upsert session in history panel (6.4)
          setSessions((prev) =>
            upsertEntry(prev, {
              id: event.session_id,
              preview: content,
              date: new Date().toISOString(),
            }),
          );
          receivedDone = true;
        } else if (event.type === 'error') {
          // Remove the placeholder assistant message on error
          setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId));
          setStreamError({ message: event.error, retryable: event.retryable });
          if (event.retryable) {
            setFailedMessage(content);
          }
          receivedDone = true;
        }
      }

      // Post-loop: detect stream interruption (no done/error event received)
      if (!receivedDone) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId && m.content !== ''
              ? { ...m, content: m.content + `\n\n${t('responseInterrupted')}`, interrupted: true }
              : m,
          ),
        );
      }
    } catch (err) {
      // If 401, session expired — redirect to login
      if ((err as { status?: number })?.status === 401) {
        window.location.href = `/${locale}/login`;
        return;
      }

      // If aborted by user, just clean up silently
      if (err instanceof DOMException && err.name === 'AbortError') {
        // Remove the placeholder assistant message if it's still empty
        setMessages((prev) =>
          prev.filter((m) => !(m.id === assistantMsgId && m.content === '')),
        );
        return;
      }

      // Remove the placeholder assistant message and the optimistic user message on failure
      setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId && m.id !== userMsg.id));
      // Restore input text (Req 9.2)
      setInput(content);

      // Show retry-capable error for HTTP 500 or timeout (Req 9.3)
      if (isRetryableError(err)) {
        setFailedMessage(content);
        setError(t('errorSendRetry'));
      } else {
        setError(t('errorSend'));
      }
    } finally {
      setLoading(false);
      setStreaming(false);
      abortControllerRef.current = null;
    }
  }

  // Retry handler (Req 9.4)
  function handleRetry() {
    if (!failedMessage) return;
    const content = failedMessage;
    setFailedMessage(null);
    setError('');
    setStreamError(null);
    setInput('');
    void handleSend(content);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  async function handleNewSession() {
    // Case 1: Stream in progress — abort and clear immediately (skip verification)
    if (streaming) {
      abortControllerRef.current?.abort();
      clearStoredSessionId();
      const newId = generateSessionId();
      setSessionId(newId);
      setMessages([]);
      setError('');
      setStreamError(null);
      setFailedMessage(null);
      setInput('');
      return;
    }

    // Case 2: No messages — proceed with synchronous reset (no backend call needed)
    if (messages.length === 0) {
      clearStoredSessionId();
      const newId = generateSessionId();
      setSessionId(newId);
      setMessages([]);
      setError('');
      setStreamError(null);
      setFailedMessage(null);
      setInput('');
      return;
    }

    // Case 3: Messages exist, no stream — verify session on backend before clearing
    setVerifying(true);
    setError('');
    try {
      const verifyController = new AbortController();
      const timeoutId = setTimeout(() => verifyController.abort(), 3000);
      try {
        await apiClient.chat.getHistory(sessionId, verifyController.signal);
      } finally {
        clearTimeout(timeoutId);
      }
      // Verification succeeded — safe to clear
      clearStoredSessionId();
      const newId = generateSessionId();
      setSessionId(newId);
      setMessages([]);
      setStreamError(null);
      setFailedMessage(null);
      setInput('');
    } catch {
      // Verification failed (network error, 404, timeout) — preserve messages
      setError(t('newSessionVerifyFailed'));
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div className="flex h-screen">
      <SessionHistoryPanel
        entries={sessions}
        activeId={sessionId}
        loading={sessionsLoading}
        error={sessionsError}
        hasMore={sessionsHasMore}
        loadingMore={sessionsLoadingMore}
        onLoadMore={handleLoadMore}
        onSelect={handleSessionSelect}
        onDelete={handleSessionDelete}
        selectingId={selectingId}
        deleteMode="confirm"
        panelTitle={tHistory('chatTitle')}
        emptyMessage={tHistory('empty')}
        deleteLabel={tHistory('delete')}
        announceMessage={announceMessage}
        operationError={operationError}
        confirmDeleteTitle={tHistory('confirmDeleteTitle')}
        confirmDeleteMessage={tHistory('confirmDeleteMessage')}
        confirmDeleteLabel={tHistory('confirm')}
        cancelDeleteLabel={tHistory('cancel')}
      />
      <main className="flex flex-col flex-1 h-screen max-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white border-b px-6 py-3 flex items-center justify-between shrink-0">
        <h1 className="text-lg font-bold text-gray-900">{t('title')}</h1>
        <button
          type="button"
          onClick={() => void handleNewSession()}
          disabled={verifying}
          className="text-sm text-blue-600 hover:underline disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
        >
          {verifying && (
            <span className="inline-block w-3 h-3 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" aria-hidden="true" />
          )}
          {t('newSession')}
        </button>
      </header>

      {/* Streaming cursor CSS */}
      <style>{`
        .streaming-cursor::after {
          content: '|';
          display: inline;
          animation: blink-cursor 0.8s step-end infinite;
          font-weight: bold;
        }
        @keyframes blink-cursor {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>

      {/* Messages area */}
      <div
        ref={messagesContainerRef}
        onScroll={handleMessagesScroll}
        className="flex-1 overflow-y-auto px-4 py-4 space-y-3"
      >
        {loadingHistory && (
          <div className="flex justify-center py-4">
            <p className="text-xs text-gray-500 italic">{t('loadingHistory')}</p>
          </div>
        )}
        {messages.length === 0 && !loadingHistory && (
          <div
            className="flex flex-col items-center justify-center h-full text-center px-4"
            data-testid="chat-empty-state"
          >
            <svg
              className="w-16 h-16 text-gray-300 mb-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.5}
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M8.625 9.75a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375m-13.5 3.01c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.184-4.183a1.14 1.14 0 0 1 .778-.332 48.294 48.294 0 0 0 5.83-.498c1.585-.233 2.708-1.626 2.708-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z"
              />
            </svg>
            <h2 className="text-lg font-semibold text-gray-500 mb-1">
              {t('emptyStateTitle')}
            </h2>
            <p className="text-sm text-gray-400">
              {t('emptyStatePrompt')}
            </p>
          </div>
        )}
        {messages.map((msg, idx) => {
          const isStreamingMsg = streaming && msg.role === 'assistant' && msg === messages[messages.length - 1] && msg.content !== '';
          // Find the previous user message for Topic Guard feedback
          const previousUserMessage = msg.role === 'assistant'
            ? messages.slice(0, idx).reverse().find((m) => m.role === 'user')?.content
            : undefined;
          return (
            <MessageBubble
              key={msg.id}
              message={msg}
              isStreaming={isStreamingMsg}
              previousUserMessage={previousUserMessage}
              apiClient={apiClient}
            />
          );
        })}
        {loading && !receivedFirstToken && <ConnectingBubble key="connecting" />}
        {loading && receivedFirstToken && streaming && messages.length > 0 && messages[messages.length - 1].role === 'assistant' && messages[messages.length - 1].content === '' && (
          <ThinkingBubble key="thinking" />
        )}
        <div key="scroll-anchor" ref={bottomRef} />
      </div>

      {/* Error with optional Retry button */}
      {error && (
        <div className="px-4 pb-2 shrink-0">
          <div role="alert" className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2 flex items-center justify-between gap-2">
            <span>{error}</span>
            {failedMessage && (
              <button
                type="button"
                onClick={handleRetry}
                className="text-xs font-medium text-red-700 bg-red-100 hover:bg-red-200 border border-red-300 rounded px-2 py-0.5 shrink-0 transition-colors"
              >
                {t('retry')}
              </button>
            )}
          </div>
        </div>
      )}
      {streamError && (
        <div className="px-4 pb-2 shrink-0">
          <div role="alert" className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2 flex items-center justify-between gap-2">
            <span>{streamError.message}</span>
            {streamError.retryable && failedMessage && (
              <button
                type="button"
                onClick={handleRetry}
                className="text-xs font-medium text-red-700 bg-red-100 hover:bg-red-200 border border-red-300 rounded px-2 py-0.5 shrink-0 transition-colors"
              >
                {t('retry')}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Input area */}
      <div className="bg-white border-t px-4 py-3 flex gap-2 items-end shrink-0">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t('placeholder')}
          rows={1}
          className="flex-1 border rounded-xl px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 max-h-32 overflow-y-auto"
          style={{ minHeight: '40px' }}
          disabled={loading || streaming}
          aria-label={t('placeholder')}
          autoFocus
        />
        <button
          type="button"
          onClick={() => void handleSend()}
          disabled={loading || streaming || !input.trim()}
          className="bg-blue-600 text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
          aria-label={t('send')}
        >
          {t('send')}
        </button>
      </div>
    </main>
    </div>
  );
}
