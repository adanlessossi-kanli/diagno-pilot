'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { createApiClient } from '@diagno-pilot/api-client';
import type { StreamEvent } from '@diagno-pilot/api-client';
import type { ChatMessage, PatientProfile, DocumentSource } from '@diagno-pilot/types';
import { useAuth } from '../../../contexts/AuthContext';
import { CitationChip } from '../../../components/CitationChip';

// ─── Types ────────────────────────────────────────────────────────────────────

type PatientMode = 'none' | 'select' | 'oneshot';

// ─── Constants ────────────────────────────────────────────────────────────────

const SESSION_STORAGE_KEY = 'diagno-pilot-chat-session';

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

function SourcesPanel({ sources }: { sources: DocumentSource[] }) {
  const t = useTranslations('chat');
  const [open, setOpen] = useState(false);

  if (sources.length === 0) return null;

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-xs text-blue-600 hover:underline flex items-center gap-1"
        aria-expanded={open}
      >
        <span>{t('sources')} ({sources.length})</span>
        <span aria-hidden="true">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {sources.map((src, i) => (
            <CitationChip
              key={`${src.document_id}-${i}`}
              index={i + 1}
              source={src}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function MessageBubble({ message, isStreaming }: { message: ChatMessage; isStreaming?: boolean }) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
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
            <span
              className="streaming-cursor"
              aria-hidden="true"
            />
          )}
        </div>
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="px-1">
            <SourcesPanel sources={message.sources} />
          </div>
        )}
        <p className={`text-xs text-gray-400 mt-1 px-1 ${isUser ? 'text-right' : 'text-left'}`}>
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
    </div>
  );
}

function ThinkingBubble() {
  const t = useTranslations('chat');
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

// ─── Patient context panel ────────────────────────────────────────────────────

interface PatientContextPanelProps {
  patientMode: PatientMode;
  setPatientMode: (m: PatientMode) => void;
  patients: PatientProfile[];
  loadingPatients: boolean;
  patientsError: string;
  selectedPatientId: string;
  setSelectedPatientId: (id: string) => void;
  oneShotPatient: { fullName: string; dateOfBirth: string; weightKg: string; allergies: string };
  setOneShotPatient: React.Dispatch<React.SetStateAction<{ fullName: string; dateOfBirth: string; weightKg: string; allergies: string }>>;
  attachedPatientLabel: string | null;
}

function PatientContextPanel({
  patientMode,
  setPatientMode,
  patients,
  loadingPatients,
  patientsError,
  selectedPatientId,
  setSelectedPatientId,
  oneShotPatient,
  setOneShotPatient,
  attachedPatientLabel,
}: PatientContextPanelProps) {
  const t = useTranslations('chat');

  return (
    <div className="border-b bg-gray-50 px-4 py-3 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">{t('attachPatient')}:</span>
        {(['none', 'select', 'oneshot'] as PatientMode[]).map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() => setPatientMode(mode)}
            className={`px-2.5 py-1 rounded text-xs font-medium border transition-colors ${
              patientMode === mode
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-100'
            }`}
          >
            {mode === 'none' && t('noPatient')}
            {mode === 'select' && t('selectPatient')}
            {mode === 'oneshot' && t('oneShotMode')}
          </button>
        ))}
        {attachedPatientLabel && (
          <span className="text-xs text-green-700 bg-green-50 border border-green-200 rounded px-2 py-0.5">
            ✓ {t('patientAttached')}: {attachedPatientLabel}
          </span>
        )}
      </div>

      {patientMode === 'select' && (
        <div>
          {loadingPatients && <p className="text-xs text-gray-500">{t('loadingPatients')}</p>}
          {patientsError && <p className="text-xs text-red-600">{patientsError}</p>}
          {!loadingPatients && !patientsError && (
            <select
              value={selectedPatientId}
              onChange={(e) => setSelectedPatientId(e.target.value)}
              className="w-full max-w-xs border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">— {t('selectPatient')} —</option>
              {patients.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.fullName ?? p.id}
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {patientMode === 'oneshot' && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-0.5">{t('patientName')}</label>
            <input
              type="text"
              value={oneShotPatient.fullName}
              onChange={(e) => setOneShotPatient((p) => ({ ...p, fullName: e.target.value }))}
              className="w-full border rounded px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-0.5">{t('dateOfBirth')}</label>
            <input
              type="date"
              value={oneShotPatient.dateOfBirth}
              onChange={(e) => setOneShotPatient((p) => ({ ...p, dateOfBirth: e.target.value }))}
              className="w-full border rounded px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-0.5">{t('weightKg')}</label>
            <input
              type="number"
              min={0}
              step={0.1}
              value={oneShotPatient.weightKg}
              onChange={(e) => setOneShotPatient((p) => ({ ...p, weightKg: e.target.value }))}
              className="w-full border rounded px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-0.5">{t('allergiesLabel')}</label>
            <input
              type="text"
              value={oneShotPatient.allergies}
              onChange={(e) => setOneShotPatient((p) => ({ ...p, allergies: e.target.value }))}
              className="w-full border rounded px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const t = useTranslations('chat');
  const locale = useLocale();
  const { user } = useAuth();

  const apiClient = useMemo(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
    return createApiClient(baseUrl);
  }, []);

  // Session — restore from localStorage or generate new
  const [sessionId, setSessionId] = useState<string>(() => {
    const stored = getStoredSessionId();
    return stored ?? generateSessionId();
  });

  // Messages
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState('');
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Retry state: stores the failed message content for retry capability
  const [failedMessage, setFailedMessage] = useState<string | null>(null);
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

  // Patient context
  const [patientMode, setPatientMode] = useState<PatientMode>('none');
  const [patients, setPatients] = useState<PatientProfile[]>([]);
  const [loadingPatients, setLoadingPatients] = useState(false);
  const [patientsError, setPatientsError] = useState('');
  const [selectedPatientId, setSelectedPatientId] = useState('');
  const [oneShotPatient, setOneShotPatient] = useState({
    fullName: '',
    dateOfBirth: '',
    weightKg: '',
    allergies: '',
  });

  // Auto-scroll refs
  const bottomRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);

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

  // Fetch patients when select mode is chosen
  const fetchPatients = useCallback(async () => {
    setLoadingPatients(true);
    setPatientsError('');
    try {
      const list = await apiClient.patients.listAllPatients();
      setPatients(list);
    } catch {
      setPatientsError(t('errorFetch'));
    } finally {
      setLoadingPatients(false);
    }
  }, [t, apiClient]);

  useEffect(() => {
    if (patientMode === 'select') {
      void fetchPatients();
    }
  }, [patientMode, fetchPatients]);

  // Build patient profile from current mode
  function buildPatientProfile(): PatientProfile | undefined {
    if (patientMode === 'select' && selectedPatientId) {
      return patients.find((p) => p.id === selectedPatientId);
    }
    if (patientMode === 'oneshot') {
      const allergies = oneShotPatient.allergies
        ? oneShotPatient.allergies.split(',').map((a) => a.trim()).filter(Boolean)
        : [];
      return {
        fullName: oneShotPatient.fullName || undefined,
        dateOfBirth: oneShotPatient.dateOfBirth || undefined,
        weightKg: oneShotPatient.weightKg ? parseFloat(oneShotPatient.weightKg) : undefined,
        allergies,
        renalFailure: false,
        hepaticFailure: false,
        currentMedications: [],
      };
    }
    return undefined;
  }

  // Label shown when a patient is attached
  const attachedPatientLabel: string | null = (() => {
    if (patientMode === 'select' && selectedPatientId) {
      const p = patients.find((pt) => pt.id === selectedPatientId);
      return p?.fullName ?? selectedPatientId;
    }
    if (patientMode === 'oneshot' && oneShotPatient.fullName) {
      return oneShotPatient.fullName;
    }
    return null;
  })();

  // Send message
  async function handleSend(retryContent?: string) {
    const content = retryContent ?? input.trim();
    if (!content || loading || streaming) return;

    setError('');
    setStreamError(null);
    setFailedMessage(null);
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
      const patientContext = buildPatientProfile();
      const stream = apiClient.chat.sendMessageStream(sessionId, content, patientContext, controller.signal);

      for await (const event of stream) {
        if (event.type === 'token') {
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
        } else if (event.type === 'error') {
          // Remove the placeholder assistant message on error
          setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId));
          setStreamError({ message: event.error, retryable: event.retryable });
          if (event.retryable) {
            setFailedMessage(content);
          }
        }
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

  function handleNewSession() {
    abortControllerRef.current?.abort();
    clearStoredSessionId();
    const newId = generateSessionId();
    setSessionId(newId);
    setMessages([]);
    setError('');
    setStreamError(null);
    setFailedMessage(null);
    setInput('');
  }

  return (
    <main className="flex flex-col h-screen max-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white border-b px-6 py-3 flex items-center justify-between shrink-0">
        <h1 className="text-lg font-bold text-gray-900">{t('title')}</h1>
        <button
          type="button"
          onClick={handleNewSession}
          className="text-sm text-blue-600 hover:underline"
        >
          {t('newSession')}
        </button>
      </header>

      {/* Patient context panel — hidden for guests */}
      {user?.role !== 'guest' && (
        <PatientContextPanel
          patientMode={patientMode}
          setPatientMode={setPatientMode}
          patients={patients}
          loadingPatients={loadingPatients}
          patientsError={patientsError}
          selectedPatientId={selectedPatientId}
          setSelectedPatientId={setSelectedPatientId}
          oneShotPatient={oneShotPatient}
          setOneShotPatient={setOneShotPatient}
          attachedPatientLabel={attachedPatientLabel}
        />
      )}

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
        {messages.map((msg) => {
          const isStreamingMsg = streaming && msg.role === 'assistant' && msg === messages[messages.length - 1] && msg.content !== '';
          return (
            <MessageBubble key={msg.id} message={msg} isStreaming={isStreamingMsg} />
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
          disabled={loading || streaming}
          aria-label={t('placeholder')}
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
  );
}
