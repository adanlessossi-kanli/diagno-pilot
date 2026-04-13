'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslations } from 'next-intl';
import Image from 'next/image';
import Link from 'next/link';
import { useLocale } from 'next-intl';
import { createApiClient } from '@diagno-pilot/api-client';
import type { DiagnosisResponse, DiagnoseSession, PrescriptionResponse } from '@diagno-pilot/api-client';
import type { PatientProfile, Symptom } from '@diagno-pilot/types';
import { StepProgress } from '@diagno-pilot/ui';
import { useAuth } from '../../../contexts/AuthContext';
import { PrescriptionStep } from './PrescriptionStep';
import { Toast } from '../../../components/Toast';
import { ConfirmDialog } from '../../../components/ConfirmDialog';
import { IMAGES } from '@/lib/images';
import { SessionHistoryPanel, prependEntry } from '../../../components/SessionHistoryPanel';
import type { SessionEntry } from '../../../components/SessionHistoryPanel';
import BackToTop from '../../../components/BackToTop';
import { buildErrorMessage } from '../../../utils/errorMessages';
import { useRequestTimeout } from '../../../hooks/useRequestTimeout';

// ─── Types ────────────────────────────────────────────────────────────────────

type InputMode = 'freeText' | 'structured';
type PatientMode = 'none' | 'select' | 'oneshot';

interface StructuredSymptom {
  name: string;
  severity: string;
  durationDays: number;
}

// ─── Zod schema ───────────────────────────────────────────────────────────────

const diagnoseSchema = z.object({
  freeText: z.string().min(3, 'Le texte doit contenir au moins 3 caractères'),
});

type DiagnoseFormValues = z.infer<typeof diagnoseSchema>;

// ─── Page ─────────────────────────────────────────────────────────────────────

function mapSessionToPartialResponse(session: DiagnoseSession): DiagnosisResponse {
  return {
    sessionId: session.id,
    diagnoses: session.diagnoses.map((d) => ({
      condition: d.condition,
      probability: d.probability,
      icdCode: d.icdCode ?? undefined,
      matchingSymptoms: d.concordantSymptoms,
      concordantSymptoms: d.concordantSymptoms,
    })),
    confidenceScore: undefined,
    llmUsed: undefined,
    sources: [],
    warningsPresent: false,
    fallbackWarning: undefined,
    degradedWarning: undefined,
    parseFailed: false,
    agentContributions: [],
    evidenceCitations: [],
  };
}

export default function DiagnosePage() {
  const t = useTranslations('diagnose');
  const tCommon = useTranslations('common');
  const tHistory = useTranslations('sessionHistory');
  const tErrors = useTranslations('errors');
  const { user } = useAuth();
  const locale = useLocale();
  const { startTimer, clearTimer, isWarning, isAborted } = useRequestTimeout();

  const apiClient = useMemo(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
    return createApiClient(baseUrl, undefined, () => locale);
  }, [locale]);

  // Symptom input state
  const [inputMode, setInputMode] = useState<InputMode>('freeText');
  const [structuredSymptoms, setStructuredSymptoms] = useState<StructuredSymptom[]>([]);
  const [newSymptom, setNewSymptom] = useState<StructuredSymptom>({ name: '', severity: 'moderate', durationDays: 1 });

  // Patient context state
  const [patientMode, setPatientMode] = useState<PatientMode>('none');
  const [patients, setPatients] = useState<PatientProfile[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState('');
  const [loadingPatients, setLoadingPatients] = useState(false);
  const [patientsError, setPatientsError] = useState('');
  const [oneShotPatient, setOneShotPatient] = useState({
    fullName: '',
    dateOfBirth: '',
    weightKg: '',
    allergies: '',
  });

  // Results state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [results, setResults] = useState<DiagnosisResponse | null>(null);
  const [showSuccessToast, setShowSuccessToast] = useState(false);
  const [antibiotics, setAntibiotics] = useState<string[]>([]);
  const [restoredPartial, setRestoredPartial] = useState(false);

  // ─── Consultation history state ─────────────────────────────────────────────
  const [consultations, setConsultations] = useState<SessionEntry[]>([]);
  const [consultationsLoading, setConsultationsLoading] = useState(false);
  const [consultationsError, setConsultationsError] = useState<string | null>(null);
  const [consultationsHasMore, setConsultationsHasMore] = useState(true);
  const consultationsPageRef = useRef(1);
  const [consultationsLoadingMore, setConsultationsLoadingMore] = useState(false);
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set());
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [announceMessage, setAnnounceMessage] = useState<string | null>(null);
  const [showNewDiagnosisConfirm, setShowNewDiagnosisConfirm] = useState(false);

  // sessionStorage key for persisting diagnose session ID
  const sessionStorageKey = `diagno-pilot-diagnose-session-${user?.id ?? 'anonymous'}`;

  // react-hook-form for free text mode
  const {
    register,
    watch,
    reset: resetForm,
    formState: { errors: formErrors },
  } = useForm<DiagnoseFormValues>({
    resolver: zodResolver(diagnoseSchema),
    mode: 'onChange',
    defaultValues: { freeText: '' },
  });

  const freeTextValue = watch('freeText');

  // Sync token from cookie on mount (best-effort)
  useEffect(() => {
    if (user) {
      // Token is managed in-memory by AuthContext
    }
  }, [user]);

  // Fetch available antibiotics on mount
  useEffect(() => {
    apiClient.diagnose.listAntibiotics()
      .then(setAntibiotics)
      .catch(() => {/* non-critical */});
  }, [apiClient]);

  // Restore partial results from sessionStorage on mount
  useEffect(() => {
    const storedSessionId = sessionStorage.getItem(sessionStorageKey);
    if (!storedSessionId) return;

    let cancelled = false;
    try {
      const promise = apiClient.diagnose.getSession(storedSessionId);
      if (!promise || typeof promise.then !== 'function') {
        // getSession returned a non-thenable — clear stale key
        sessionStorage.removeItem(sessionStorageKey);
        return;
      }
      promise
        .then((session: DiagnoseSession) => {
          if (cancelled) return;
          const partial = mapSessionToPartialResponse(session);
          setResults(partial);
          setRestoredPartial(true);
        })
        .catch(() => {
          if (cancelled) return;
          // Session expired or network error — clear and show empty form
          sessionStorage.removeItem(sessionStorageKey);
        });
    } catch {
      // getSession call failed synchronously — clear and show empty form
      sessionStorage.removeItem(sessionStorageKey);
    }

    return () => { cancelled = true; };
  }, [apiClient, sessionStorageKey]);

  // Fetch patients when "select" mode is chosen
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

  // ─── Fetch consultations on mount (8.1) ─────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setConsultationsLoading(true);
    setConsultationsError(null);
    apiClient.diagnose.listMyConsultations(1, 20)
      .then((res) => {
        if (cancelled) return;
        const mapped: SessionEntry[] = res.items.map((c) => ({
          id: c.id,
          preview: c.diagnoses[0]?.condition ?? '',
          date: c.createdAt ?? '',
        }));
        setConsultations(mapped);
        setConsultationsHasMore(mapped.length < res.total);
        consultationsPageRef.current = 1;
      })
      .catch(() => {
        if (!cancelled) setConsultationsError(tHistory('errorFetch'));
      })
      .finally(() => {
        if (!cancelled) setConsultationsLoading(false);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Load more consultations (8.1) ──────────────────────────────────────────
  const handleLoadMore = useCallback(async () => {
    if (consultationsLoadingMore || !consultationsHasMore) return;
    setConsultationsLoadingMore(true);
    try {
      const nextPage = consultationsPageRef.current + 1;
      const res = await apiClient.diagnose.listMyConsultations(nextPage, 20);
      const mapped: SessionEntry[] = res.items.map((c) => ({
        id: c.id,
        preview: c.diagnoses[0]?.condition ?? '',
        date: c.createdAt ?? '',
      }));
      setConsultations((prev) => {
        const existingIds = new Set(prev.map((e) => e.id));
        const deduped = mapped.filter((e) => !existingIds.has(e.id));
        return [...prev, ...deduped];
      });
      const loadedCount = (consultationsPageRef.current * 20) + mapped.length;
      setConsultationsHasMore(loadedCount < res.total);
      consultationsPageRef.current = nextPage;
    } catch {
      // Silently fail on load-more — user can scroll again
    } finally {
      setConsultationsLoadingMore(false);
    }
  }, [consultationsLoadingMore, consultationsHasMore, apiClient]);

  // ─── Consultation select handler (8.2) ──────────────────────────────────────
  const handleConsultationSelect = useCallback(async (id: string) => {
    setOperationError(null);
    setSelectingId(id);
    try {
      const session = await apiClient.diagnose.getSession(id);
      const partial = mapSessionToPartialResponse(session);
      setResults(partial);
      sessionStorage.setItem(sessionStorageKey, id);
      setAnnounceMessage(tHistory('sessionLoaded'));
    } catch {
      setOperationError(tHistory('errorLoad'));
    } finally {
      setSelectingId(null);
    }
  }, [apiClient, sessionStorageKey, tHistory]);

  // ─── Consultation hide handler (8.3) ────────────────────────────────────────
  const handleConsultationHide = useCallback((id: string) => {
    setHiddenIds((prev) => new Set(prev).add(id));
    // If hidden consultation is currently displayed, clear results
    const currentSessionId = sessionStorage.getItem(sessionStorageKey);
    if (currentSessionId === id) {
      setResults(null);
      sessionStorage.removeItem(sessionStorageKey);
    }
    setAnnounceMessage(tHistory('sessionHidden'));
  }, [sessionStorageKey, tHistory]);

  // ─── Determine if submit should be disabled ──────────────────────────────────

  function isSubmitDisabled(): boolean {
    if (loading) return true;
    if (inputMode === 'freeText') {
      return !freeTextValue || freeTextValue.trim().length < 3;
    }
    return structuredSymptoms.length === 0;
  }

  // ─── Symptom helpers ────────────────────────────────────────────────────────

  function addStructuredSymptom() {
    if (!newSymptom.name.trim()) return;
    setStructuredSymptoms((prev) => [...prev, { ...newSymptom }]);
    setNewSymptom({ name: '', severity: 'moderate', durationDays: 1 });
  }

  function removeSymptom(index: number) {
    setStructuredSymptoms((prev) => prev.filter((_, i) => i !== index));
  }

  // ─── Build payload ──────────────────────────────────────────────────────────

  function buildSymptoms(): Symptom[] {
    if (inputMode === 'freeText') {
      if (!freeTextValue?.trim()) return [];
      return [{ name: freeTextValue.trim(), severity: 'moderate', durationDays: 0 }];
    }
    return structuredSymptoms.map((s) => ({
      name: s.name,
      severity: s.severity,
      durationDays: s.durationDays,
    }));
  }

  function buildPatientProfile(): PatientProfile | undefined {
    if (patientMode === 'select' && selectedPatientId) {
      const found = patients.find((p) => p.id === selectedPatientId);
      return found ?? undefined;
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

  // ─── Submit ─────────────────────────────────────────────────────────────────

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setResults(null);
    setRestoredPartial(false);

    const symptoms = buildSymptoms();
    if (symptoms.length === 0) {
      setError(t('noSymptoms'));
      return;
    }

    // Clear old session ID before new submission
    sessionStorage.removeItem(sessionStorageKey);

    setLoading(true);
    const controller = new AbortController();
    startTimer(controller);
    try {
      const patientProfile = buildPatientProfile();
      const response = await apiClient.diagnose.getSymptomsDiagnosis(symptoms, patientProfile);
      setResults(response);
      setShowSuccessToast(true);

      // Persist new session ID to sessionStorage
      if (response.sessionId) {
        sessionStorage.setItem(sessionStorageKey, response.sessionId);

        // Prepend new consultation to history list (8.4)
        const newEntry: SessionEntry = {
          id: response.sessionId,
          preview: response.diagnoses[0]?.condition ?? '',
          date: new Date().toISOString(),
        };
        setConsultations((prev) => prependEntry(prev, newEntry));
      }
    } catch {
      const { descriptionKey, actionKey } = buildErrorMessage('network');
      const descKey = descriptionKey.replace('errors.', '') as Parameters<typeof tErrors>[0];
      const actKey = actionKey.replace('errors.', '') as Parameters<typeof tErrors>[0];
      setError(`${tErrors(descKey)} ${tErrors(actKey)}`);
    } finally {
      clearTimer();
      setLoading(false);
    }
  }

  // ─── Prescription handler ────────────────────────────────────────────────────

  async function handleGetPrescription(antibiotic: string): Promise<PrescriptionResponse> {
    const patientProfile = buildPatientProfile() ?? {
      allergies: [],
      renalFailure: false,
      hepaticFailure: false,
      currentMedications: [],
    };
    return apiClient.diagnose.getPrescription(antibiotic, patientProfile);
  }

  async function handleGetLLMPrescription(condition: string): Promise<string> {
    const sessionId = `rx-${Date.now()}`;
    const patientProfile = buildPatientProfile();
    const patientCtx = patientProfile
      ? ` Patient: ${patientProfile.allergies?.length ? `allergies: ${patientProfile.allergies.join(', ')}` : 'no known allergies'}.`
      : '';
    const prompt = `En tant que médecin, propose un protocole de traitement pour le diagnostic "${condition}".${patientCtx} Inclus les médicaments, posologies, durée et précautions. Réponds de manière structurée.`;
    let answer = '';
    for await (const event of apiClient.chat.sendMessageStream(sessionId, prompt, patientProfile ?? undefined)) {
      if (event.type === 'token') {
        answer += event.content;
      } else if (event.type === 'done') {
        return event.answer;
      } else if (event.type === 'error') {
        throw new Error(event.error);
      }
    }
    return answer;
  }

  // ─── New diagnosis ───────────────────────────────────────────────────────────

  function handleNewDiagnosis() {
    setResults(null);
    setRestoredPartial(false);
    setError('');
    setShowSuccessToast(false);
    resetForm({ freeText: '' });
    setStructuredSymptoms([]);
    setNewSymptom({ name: '', severity: 'moderate', durationDays: 1 });
    setInputMode('freeText');
    sessionStorage.removeItem(sessionStorageKey);
  }

  // ─── Render ─────────────────────────────────────────────────────────────────

  // Derive activeId from sessionStorage
  const activeConsultationId = typeof window !== 'undefined' ? sessionStorage.getItem(sessionStorageKey) : null;

  // Filter out hidden entries
  const visibleConsultations = consultations.filter((e) => !hiddenIds.has(e.id));

  // Compute current step index for StepProgress
  const currentStepIndex = useMemo(() => {
    if (!results) return 0;
    if (!results.parseFailed && results.diagnoses.length > 0) return 2;
    return 1;
  }, [results]);

  return (
    <div className="flex h-screen">
      <SessionHistoryPanel
        entries={visibleConsultations}
        activeId={activeConsultationId}
        loading={consultationsLoading}
        error={consultationsError}
        hasMore={consultationsHasMore}
        loadingMore={consultationsLoadingMore}
        onLoadMore={handleLoadMore}
        onSelect={handleConsultationSelect}
        onDelete={handleConsultationHide}
        selectingId={selectingId}
        deleteMode="instant"
        panelTitle={tHistory('diagnoseTitle')}
        emptyMessage={tHistory('emptyDiagnose')}
        deleteLabel={tHistory('hide')}
        announceMessage={announceMessage}
        operationError={operationError}
        confirmDeleteTitle={tHistory('confirmDeleteTitle')}
        confirmDeleteMessage={tHistory('confirmDeleteMessage')}
        confirmDeleteLabel={tHistory('confirm')}
        cancelDeleteLabel={tHistory('cancel')}
      />
      <main className="flex-1 min-h-screen p-8 max-w-3xl mx-auto overflow-y-auto">
      {/* Header illustration */}
      <div className="relative w-full h-32 mb-6 rounded-lg overflow-hidden bg-gray-100">
        <Image
          src={IMAGES.diagnoseHeader.src}
          alt={IMAGES.diagnoseHeader.alt}
          fill
          priority
          className="object-cover"
          sizes="(max-width: 768px) 100vw, 768px"
        />
      </div>

      <StepProgress
        steps={[t('stepSymptoms'), t('stepResults'), t('stepPrescription')]}
        currentIndex={currentStepIndex}
      />

      <h1 className="text-2xl font-bold mb-6 flex items-center justify-between">
        {t('title')}
        {results && (
          <button
            type="button"
            onClick={() => setShowNewDiagnosisConfirm(true)}
            className="text-sm font-medium text-blue-600 hover:underline"
          >
            + {t('newDiagnosis')}
          </button>
        )}
      </h1>

      <ConfirmDialog
        open={showNewDiagnosisConfirm}
        title={t('confirmNewDiagnosis')}
        message={t('confirmNewDiagnosisMessage')}
        confirmLabel={tCommon('confirm')}
        cancelLabel={tCommon('cancel')}
        onConfirm={() => {
          setShowNewDiagnosisConfirm(false);
          handleNewDiagnosis();
        }}
        onCancel={() => setShowNewDiagnosisConfirm(false)}
      />

      {showSuccessToast && (
        <Toast
          message={t('successDiagnose')}
          type="success"
          duration={3000}
          onClose={() => setShowSuccessToast(false)}
        />
      )}

      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-6">

        {/* ── Symptom input section ── */}
        <section className="border rounded-lg p-6 space-y-4">
          <h2 className="text-lg font-semibold">{t('symptoms')}</h2>

          {/* Mode toggle */}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setInputMode('freeText')}
              className={`px-3 py-1.5 rounded text-sm font-medium border transition-colors ${
                inputMode === 'freeText'
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
              }`}
            >
              {t('freeText')}
            </button>
            <button
              type="button"
              onClick={() => setInputMode('structured')}
              className={`px-3 py-1.5 rounded text-sm font-medium border transition-colors ${
                inputMode === 'structured'
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
              }`}
            >
              {t('structured')}
            </button>
          </div>

          {/* Free text input */}
          {inputMode === 'freeText' && (
            <div>
              <textarea
                {...register('freeText')}
                className="w-full border rounded px-3 py-2 h-28 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder={t('symptomsPlaceholder')}
                autoFocus
              />
              {formErrors.freeText && (
                <p role="alert" className="text-xs text-red-600 mt-1">
                  {formErrors.freeText.message}
                </p>
              )}
            </div>
          )}

          {/* Structured symptom list */}
          {inputMode === 'structured' && (
            <div className="space-y-3">
              {/* Existing symptoms */}
              {structuredSymptoms.length > 0 && (
                <ul className="space-y-2">
                  {structuredSymptoms.map((s, i) => (
                    <li key={`${s.name}-${i}`} className="flex items-center justify-between bg-gray-50 rounded px-3 py-2 text-sm">
                      <span>
                        <span className="font-medium">{s.name}</span>
                        {' — '}
                        <span className="text-gray-500">{s.severity}, {s.durationDays}j</span>
                      </span>
                      <button
                        type="button"
                        onClick={() => removeSymptom(i)}
                        className="text-red-500 hover:text-red-700 text-xs ml-2"
                        aria-label="Supprimer"
                      >
                        ✕
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {/* Add new symptom row */}
              <div className="flex gap-2 flex-wrap">
                <input
                  type="text"
                  value={newSymptom.name}
                  onChange={(e) => setNewSymptom((p) => ({ ...p, name: e.target.value }))}
                  placeholder={t('symptomName')}
                  className="flex-1 min-w-32 border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <select
                  value={newSymptom.severity}
                  onChange={(e) => setNewSymptom((p) => ({ ...p, severity: e.target.value }))}
                  className="border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="mild">{t('severityOptions.mild')}</option>
                  <option value="moderate">{t('severityOptions.moderate')}</option>
                  <option value="severe">{t('severityOptions.severe')}</option>
                </select>
                <input
                  type="number"
                  min={0}
                  value={newSymptom.durationDays}
                  onChange={(e) => setNewSymptom((p) => ({ ...p, durationDays: parseInt(e.target.value) || 0 }))}
                  placeholder={t('durationDays')}
                  className="w-24 border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button
                  type="button"
                  onClick={addStructuredSymptom}
                  className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 border border-gray-300 rounded text-sm font-medium"
                >
                  + {t('addSymptom')}
                </button>
              </div>
            </div>
          )}
        </section>

        {/* ── Patient context section ── */}
        <section className="border rounded-lg p-6 space-y-4">
          <h2 className="text-lg font-semibold">{t('patientContext')}</h2>

          <div className="flex gap-2 flex-wrap">
            {(['none', 'select', 'oneshot'] as PatientMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setPatientMode(mode)}
                className={`px-3 py-1.5 rounded text-sm font-medium border transition-colors ${
                  patientMode === mode
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                }`}
              >
                {mode === 'none' && t('noPatient')}
                {mode === 'select' && t('selectPatient')}
                {mode === 'oneshot' && t('oneShotMode')}
              </button>
            ))}
          </div>

          {/* Select existing patient */}
          {patientMode === 'select' && (
            <div>
              {loadingPatients && <p className="text-sm text-gray-500">{t('loadingPatients')}</p>}
              {patientsError && <p className="text-sm text-red-600">{patientsError}</p>}
              {!loadingPatients && !patientsError && (
                <select
                  value={selectedPatientId}
                  onChange={(e) => setSelectedPatientId(e.target.value)}
                  className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
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

          {/* One-shot patient form */}
          {patientMode === 'oneshot' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">{t('patientName')}</label>
                <input
                  type="text"
                  value={oneShotPatient.fullName}
                  onChange={(e) => setOneShotPatient((p) => ({ ...p, fullName: e.target.value }))}
                  className="w-full border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">{t('dateOfBirth')}</label>
                <input
                  type="date"
                  value={oneShotPatient.dateOfBirth}
                  onChange={(e) => setOneShotPatient((p) => ({ ...p, dateOfBirth: e.target.value }))}
                  className="w-full border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">{t('weightKg')}</label>
                <input
                  type="number"
                  min={0}
                  step={0.1}
                  value={oneShotPatient.weightKg}
                  onChange={(e) => setOneShotPatient((p) => ({ ...p, weightKg: e.target.value }))}
                  className="w-full border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">{t('allergiesLabel')}</label>
                <input
                  type="text"
                  value={oneShotPatient.allergies}
                  onChange={(e) => setOneShotPatient((p) => ({ ...p, allergies: e.target.value }))}
                  className="w-full border rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          )}
        </section>

        {/* ── Error ── */}
        {error && (
          <p role="alert" className="text-sm text-error-text bg-error-bg border border-error-border border-l-4 rounded px-3 py-2">
            {error}
          </p>
        )}

        {/* ── Timeout warning ── */}
        {isWarning && !isAborted && (
          <p role="status" className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            {tErrors('timeout')} {tErrors('timeoutAction')}
          </p>
        )}

        {/* ── Auto-cancel notice ── */}
        {isAborted && (
          <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {tErrors('autoCancel')}
          </p>
        )}

        {/* ── Submit ── */}
        <button
          type="submit"
          disabled={isSubmitDisabled()}
          className="w-full bg-blue-600 text-white px-4 py-2.5 rounded font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
        >
          {loading && (
            <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          )}
          {loading ? tCommon('loading') : t('analyze')}
        </button>
      </form>

      {/* ── Results ── */}
      {results && (
        <div className="mt-8 space-y-4">
          <section className="space-y-4">
            <h2 className="text-xl font-bold">{t('resultsTitle')}</h2>

            {/* Restored partial notice */}
            {restoredPartial && (
              <div role="status" data-testid="restored-partial-notice" className="bg-blue-50 border-l-4 border-blue-400 p-3 text-sm text-blue-800">
                ℹ️ {t('restoredPartial')}
              </div>
            )}

            {/* Warning banners */}
            {results.warningsPresent && (
              <div className="space-y-2" data-testid="warnings-section">
                {results.fallbackWarning && (
                  <div role="alert" className="bg-orange-50 border-l-4 border-orange-400 p-3 text-sm text-orange-800">
                    ⚠️ {t('fallbackWarning')}
                  </div>
                )}
                {results.degradedWarning && (
                  <div role="alert" className="bg-yellow-50 border-l-4 border-yellow-400 p-3 text-sm text-yellow-800">
                    ℹ️ {t('degradedWarning')}
                  </div>
                )}
              </div>
            )}

            {/* Parse failure warning banner (Req 25.1, 25.3, 25.4) */}
            {results.parseFailed && (
              <div role="alert" data-testid="parse-failed-warning" className="bg-red-50 border-l-4 border-red-500 p-3 text-sm text-red-800">
                ⚠️ {t('parseFailedWarning')}
              </div>
            )}


            {results.llmUsed && (
              <p className="text-xs text-gray-500">{t('llmUsed')}: {results.llmUsed}</p>
            )}

            {!results.parseFailed && (
            <div className="space-y-3">
              {results.diagnoses.map((diag, i) => {
                const pct = diag.probability;
                const borderAccent =
                  pct >= 0.7
                    ? 'border-l-4 border-l-success-border'
                    : pct >= 0.4
                    ? 'border-l-4 border-l-warning-border'
                    : 'border-l-4 border-l-error-border';
                return (
                <div key={`${diag.condition}-${i}`} className={`border rounded-lg p-4 space-y-2 ${borderAccent}`}>
                  <div className="flex items-center justify-between gap-4">
                    <h3 className="font-semibold text-gray-900">{diag.condition}</h3>
                    {diag.icdCode && (
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded font-mono">
                        {diag.icdCode}
                      </span>
                    )}
                  </div>

                  {/* Probability bar */}
                  <div>
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>{t('probability')}</span>
                      <span>{Math.round(diag.probability * 100)}%</span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className="bg-primary-600 h-2 rounded-full transition-all"
                        style={{ width: `${Math.round(diag.probability * 100)}%` }}
                        role="progressbar"
                        aria-valuenow={Math.round(diag.probability * 100)}
                        aria-valuemin={0}
                        aria-valuemax={100}
                      />
                    </div>
                  </div>

                  {/* Matching symptoms */}
                  {(diag.matchingSymptoms ?? diag.concordantSymptoms)?.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 mb-1">{t('matchingSymptoms')}</p>
                      <div className="flex flex-wrap gap-1">
                        {(diag.matchingSymptoms ?? diag.concordantSymptoms).map((s, j) => (
                          <span key={`${s}-${j}`} className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded">
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                );
              })}
            </div>
            )}

            {/* Evidence citations */}
            {results.evidenceCitations && results.evidenceCitations.length > 0 && (
              <div className="mt-4" data-testid="evidence-citations">
                <h3 className="text-sm font-semibold text-gray-600 mb-2">{t('evidenceCitations')}</h3>
                <ul className="space-y-2">
                  {results.evidenceCitations.map((citation, j) => (
                    <li key={`citation-${j}`} className="text-xs bg-gray-50 rounded px-3 py-2">
                      <span className="font-medium">{citation.title}</span>
                      <span className="text-gray-400"> — {citation.source}</span>
                      {citation.page != null && <span className="text-gray-400"> (p. {citation.page})</span>}
                      {citation.excerpt && <p className="text-gray-500 mt-1 italic">« {citation.excerpt} »</p>}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Agent contributions */}
            {results.agentContributions && results.agentContributions.length > 0 && (
              <div className="mt-4" data-testid="agent-contributions">
                <h3 className="text-sm font-semibold text-gray-600 mb-2">{t('agentContributions')}</h3>
                <div className="grid grid-cols-2 gap-2">
                  {results.agentContributions.map((agent, i) => (
                    <div key={`agent-${i}`} className="bg-gray-50 rounded px-3 py-2 text-sm">
                      <span className="font-medium">{agent.agentName}</span>
                      <span className="text-gray-500 ml-2">{Math.round(agent.confidenceScore * 100)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Sources */}
            {results.sources && results.sources.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-medium text-gray-500 mb-2">{t('sources')}</p>
                <ul className="space-y-1">
                  {results.sources.map((src, i) => (
                    <li key={`${src.title}-${i}`} className="text-xs text-gray-600 bg-gray-50 rounded px-3 py-1.5">
                      <span className="font-medium">{src.title}</span>
                      {src.section && <span className="text-gray-400"> — {src.section}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {/* ── Step 3: Prescription ── */}
          {!results.parseFailed && results.diagnoses.length > 0 && (
            <PrescriptionStep
              diagnoses={results.diagnoses}
              antibiotics={antibiotics}
              onGetPrescription={(antibiotic) => handleGetPrescription(antibiotic)}
              onGetLLMPrescription={(condition) => handleGetLLMPrescription(condition)}
            />
          )}
        </div>
      )}

      {/* History link */}
      <div className="mt-8">
        <Link
          href={`/${locale}/diagnose/history`}
          className="text-blue-600 hover:underline text-sm font-medium"
          data-testid="history-link"
        >
          {t('viewHistory')} →
        </Link>
      </div>
    </main>
    <BackToTop />
    </div>
  );
}
