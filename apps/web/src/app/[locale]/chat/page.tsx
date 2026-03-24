'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { createApiClient } from '@diagno-pilot/api-client';
import type { ChatMessage, PatientProfile, DocumentSource } from '@diagno-pilot/types';
import { useAuth } from '../../../contexts/AuthContext';

// ─── Types ────────────────────────────────────────────────────────────────────

type PatientMode = 'none' | 'select' | 'oneshot';

// ─── Helpers ──────────────────────────────────────────────────────────────────

let memoryToken: string | null = null;

function getToken(): string | null {
  return memoryToken;
}

function getApiClient() {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
  return createApiClient(baseUrl, getToken);
}

function generateSessionId(): string {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
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
        <ul className="mt-1.5 space-y-1.5">
          {sources.map((src, i) => (
            <li key={i} className="text-xs bg-blue-50 border border-blue-100 rounded px-3 py-2 space-y-0.5">
              <p className="font-semibold text-blue-800">{src.title}</p>
              {src.section && (
                <p className="text-blue-600">
                  <span className="font-medium">{t('section')}:</span> {src.section}
                </p>
              )}
              {src.excerpt && (
                <p className="text-gray-600 italic">&ldquo;{src.excerpt}&rdquo;</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
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
  const { user } = useAuth();

  // Session
  const [sessionId, setSessionId] = useState<string>(() => generateSessionId());

  // Messages
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

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

  // Auto-scroll ref
  const bottomRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Fetch patients when select mode is chosen
  const fetchPatients = useCallback(async () => {
    setLoadingPatients(true);
    setPatientsError('');
    try {
      const client = getApiClient();
      const list = await client.patients.listPatients();
      setPatients(list);
    } catch {
      setPatientsError(t('errorFetch'));
    } finally {
      setLoadingPatients(false);
    }
  }, [t]);

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
  async function handleSend() {
    const content = input.trim();
    if (!content || loading) return;

    setError('');
    setInput('');

    // Optimistically add user message
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const client = getApiClient();
      const patientContext = buildPatientProfile();
      const assistantMsg = await client.chat.sendMessage(sessionId, content, patientContext);
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setError(t('errorSend'));
      // Remove the optimistic user message on failure
      setMessages((prev) => prev.filter((m) => m.id !== userMsg.id));
      setInput(content);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  function handleNewSession() {
    setSessionId(generateSessionId());
    setMessages([]);
    setError('');
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

      {/* Patient context panel */}
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

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {loading && <ThinkingBubble />}
        <div ref={bottomRef} />
      </div>

      {/* Error */}
      {error && (
        <div className="px-4 pb-2 shrink-0">
          <p role="alert" className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {error}
          </p>
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
          disabled={loading}
          aria-label={t('placeholder')}
        />
        <button
          type="button"
          onClick={() => void handleSend()}
          disabled={loading || !input.trim()}
          className="bg-blue-600 text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
          aria-label={t('send')}
        >
          {t('send')}
        </button>
      </div>
    </main>
  );
}
