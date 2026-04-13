'use client';

/**
 * DocumentChat — RAG-powered chat interface for querying indexed medical documents.
 *
 * Streams responses via SSE, renders CitationChip components for sources,
 * and integrates with SessionHistoryPanel for session management.
 *
 * Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 9.1
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import type { createApiClient } from '@diagno-pilot/api-client';
import { CitationChip } from './CitationChip';
import type { DocumentSource } from './CitationChip';
import { SessionHistoryPanel, upsertEntry, removeEntry } from './SessionHistoryPanel';
import type { SessionEntry } from './SessionHistoryPanel';
import CopyButton from './CopyButton';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: DocumentSource[];
  timestamp: string;
  interrupted?: boolean;
}

interface DocumentChatProps {
  apiClient: ReturnType<typeof createApiClient>;
  /** Whether the user's auth token is valid */
  isAuthenticated: boolean;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const SESSION_STORAGE_KEY = 'diagno-pilot-doc-chat-session';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function generateSessionId(): string {
  return `session-doc-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
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

// ─── Sub-components ───────────────────────────────────────────────────────────

function MessageBubble({
  message,
  isStreaming,
}: {
  message: ChatMessage;
  isStreaming?: boolean;
}) {
  const isUser = message.role === 'user';

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
          {message.content}
          {isStreaming && (
            <span className="streaming-cursor" aria-hidden="true" />
          )}
        </div>
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {message.sources.map((source, idx) => (
              <CitationChip key={idx} index={idx + 1} source={source} />
            ))}
          </div>
        )}
        <p className={`text-xs text-gray-400 mt-1 px-1 ${isUser ? 'text-right' : 'text-left'}`}>
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
      {!isUser && (
        <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <CopyButton text={message.content} />
        </div>
      )}
    </div>
  );
}

function ThinkingBubble() {
  const t = useTranslations('documentChat');
  return (
    <div className="flex justify-start">
      <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-2.5">
        <span className="text-xs text-gray-500 italic">{t('thinking')}</span>
        <span className="inline-flex gap-0.5 ml-2">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </span>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function DocumentChat({ apiClient, isAuthenticated }: DocumentChatProps) {
  const t = useTranslations('documentChat');
  const tHistory = useTranslations('sessionHistory');
  const locale = useLocale();

  // Session — restore from localStorage or generate new
  const [sessionId, setSessionId] = useState<string>(() => {
    return getStoredSessionId() ?? generateSessionId();
  });

  // Messages
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState('');
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Retry state
  const [failedMessage, setFailedMessage] = useState<string | null>(null);
  // Verification state for "New Session"
  const [verifying, setVerifying] = useState(false);
  // Stream error with retryable flag
  const [streamError, setStreamError] = useState<{ message: string; retryable: boolean } | null>(null);

  // AbortController ref
  const abortControllerRef = useRef<AbortController | null>(null);

  // Abort on unmount
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

  // ─── Fetch sessions on mount ────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setSessionsLoading(true);
    setSessionsError(null);
    apiClient.documents.listChatSessions(0, 20)
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

  // ─── Load more sessions ─────────────────────────────────────────────────────
  const handleLoadMore = useCallback(async () => {
    if (sessionsLoadingMore || !sessionsHasMore) return;
    setSessionsLoadingMore(true);
    try {
      const res = await apiClient.documents.listChatSessions(sessionsPageRef.current, 20);
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
      // Silently fail on load-more
    } finally {
      setSessionsLoadingMore(false);
    }
  }, [sessionsLoadingMore, sessionsHasMore, apiClient]);

  // ─── Session select handler ─────────────────────────────────────────────────
  const handleSessionSelect = useCallback(async (id: string) => {
    setOperationError(null);
    setSelectingId(id);
    try {
      const session = await apiClient.documents.getChatHistory(id);
      const mapped: ChatMessage[] = (session?.messages ?? []).map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        sources: m.sources,
        timestamp: m.timestamp,
      }));
      setMessages(mapped);
      setSessionId(id);
      storeSessionId(id);
      setError('');
      setStreamError(null);
      setFailedMessage(null);
      setAnnounceMessage(tHistory('sessionLoaded'));
    } catch {
      setOperationError(tHistory('errorLoad'));
    } finally {
      setSelectingId(null);
    }
  }, [apiClient, tHistory]);

  // ─── Session delete handler ─────────────────────────────────────────────────
  const handleSessionDelete = useCallback(async (id: string) => {
    setOperationError(null);
    const snapshot = sessions;
    setSessions((prev) => removeEntry(prev, id));
    try {
      await apiClient.documents.deleteChatSession(id);
      setAnnounceMessage(tHistory('sessionDeleted'));
      if (id === sessionId) {
        clearStoredSessionId();
        const newId = generateSessionId();
        setSessionId(newId);
        setMessages([]);
        setError('');
        setStreamError(null);
        setFailedMessage(null);
      }
    } catch {
      setSessions(snapshot);
      setOperationError(tHistory('errorDelete'));
    }
  }, [sessions, apiClient, tHistory, sessionId]);

  // ─── Load history on mount for stored session ───────────────────────────────
  useEffect(() => {
    const stored = getStoredSessionId();
    if (!stored) return;
    let cancelled = false;
    setLoadingHistory(true);
    apiClient.documents.getChatHistory(stored)
      .then((session) => {
        if (!cancelled && session?.messages) {
          const mapped: ChatMessage[] = session.messages.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            sources: m.sources,
            timestamp: m.timestamp,
          }));
          setMessages(mapped);
        }
      })
      .catch(() => {
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

  // ─── Smart auto-scroll ─────────────────────────────────────────────────────
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

  // ─── Send message ───────────────────────────────────────────────────────────
  async function handleSend(retryContent?: string) {
    const content = retryContent ?? input.trim();
    if (!content || loading || streaming) return;

    setError('');
    setStreamError(null);
    setFailedMessage(null);
    if (!retryContent) setInput('');

    // Persist sessionId to localStorage on first message
    storeSessionId(sessionId);

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };

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

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const stream = apiClient.documents.chatStream(sessionId, content, controller.signal);

      let receivedDone = false;

      for await (const event of stream) {
        if (event.type === 'token') {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? { ...m, content: m.content + event.content }
                : m,
            ),
          );
        } else if (event.type === 'done') {
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
          // Upsert session in history panel
          setSessions((prev) =>
            upsertEntry(prev, {
              id: event.session_id,
              preview: content,
              date: new Date().toISOString(),
            }),
          );
          receivedDone = true;
        } else if (event.type === 'error') {
          setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId));
          setStreamError({ message: event.error, retryable: event.retryable });
          if (event.retryable) {
            setFailedMessage(content);
          }
          receivedDone = true;
        }
      }

      // Detect stream interruption
      if (!receivedDone) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId && m.content !== ''
              ? { ...m, content: m.content + '\n\n[Response interrupted]', interrupted: true }
              : m,
          ),
        );
      }
    } catch (err) {
      // 401 — redirect to login
      if ((err as { status?: number })?.status === 401) {
        window.location.href = `/${locale}/login`;
        return;
      }

      // AbortError — silently clean up
      if (err instanceof DOMException && err.name === 'AbortError') {
        setMessages((prev) =>
          prev.filter((m) => !(m.id === assistantMsgId && m.content === '')),
        );
        return;
      }

      // Remove placeholder and user message on failure
      setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId && m.id !== userMsg.id));
      setInput(content);

      setFailedMessage(content);
      setError(t('errorSendRetry'));
    } finally {
      setLoading(false);
      setStreaming(false);
      abortControllerRef.current = null;
    }
  }

  // ─── Retry handler ──────────────────────────────────────────────────────────
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

  // ─── New session handler ────────────────────────────────────────────────────
  async function handleNewSession() {
    // Case 1: Stream in progress — abort and clear
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

    // Case 2: No messages — just reset
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

    // Case 3: Messages exist — verify session on backend, then clear
    setVerifying(true);
    setError('');
    try {
      const verifyController = new AbortController();
      const timeoutId = setTimeout(() => verifyController.abort(), 3000);
      try {
        await apiClient.documents.getChatHistory(sessionId, verifyController.signal);
      } finally {
        clearTimeout(timeoutId);
      }
      clearStoredSessionId();
      const newId = generateSessionId();
      setSessionId(newId);
      setMessages([]);
      setStreamError(null);
      setFailedMessage(null);
      setInput('');
    } catch {
      setError(t('errorSend'));
    } finally {
      setVerifying(false);
    }
  }

  // ─── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-1 min-w-0 h-full">
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
      <main className="flex flex-col flex-1 h-full max-h-full bg-gray-100">
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
          {messages.map((msg) => {
            const isStreamingMsg = streaming && msg.role === 'assistant' && msg === messages[messages.length - 1] && msg.content !== '';
            return (
              <MessageBubble
                key={msg.id}
                message={msg}
                isStreaming={isStreamingMsg}
              />
            );
          })}
          {loading && !streaming && <ThinkingBubble key="thinking" />}
          {loading && streaming && messages.length > 0 && messages[messages.length - 1].role === 'assistant' && messages[messages.length - 1].content === '' && (
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
            disabled={loading || streaming || !isAuthenticated}
            aria-label={t('placeholder')}
            autoFocus
          />
          <button
            type="button"
            onClick={() => void handleSend()}
            disabled={loading || streaming || !input.trim() || !isAuthenticated}
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
