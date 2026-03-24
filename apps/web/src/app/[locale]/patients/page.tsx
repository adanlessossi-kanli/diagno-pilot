'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { createApiClient } from '@diagno-pilot/api-client';
import type { PatientProfile, AgeGroup } from '@diagno-pilot/types';
import { useAuth } from '../../../contexts/AuthContext';

// ─── Helpers ──────────────────────────────────────────────────────────────────

let memoryToken: string | null = null;

function getToken(): string | null {
  return memoryToken;
}

function getApiClient() {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
  return createApiClient(baseUrl, getToken);
}

function formatDate(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('fr-FR');
}

// ─── Creation form state ──────────────────────────────────────────────────────

interface CreateFormState {
  fullName: string;
  dateOfBirth: string;
  weightKg: string;
  allergies: string;
  renalFailure: boolean;
  hepaticFailure: boolean;
  currentMedications: string;
}

const EMPTY_FORM: CreateFormState = {
  fullName: '',
  dateOfBirth: '',
  weightKg: '',
  allergies: '',
  renalFailure: false,
  hepaticFailure: false,
  currentMedications: '',
};

// ─── Patient card ─────────────────────────────────────────────────────────────

function PatientCard({
  patient,
  onView,
  t,
}: {
  patient: PatientProfile;
  onView: (id: string) => void;
  t: ReturnType<typeof useTranslations<'patients'>>;
}) {
  const ageGroupLabel = patient.ageGroup
    ? t(`ageGroups.${patient.ageGroup}` as Parameters<typeof t>[0])
    : '—';

  return (
    <div className="border rounded-lg p-4 bg-white hover:shadow-sm transition-shadow flex items-center justify-between gap-4">
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-semibold text-gray-900 truncate">{patient.fullName ?? '—'}</p>
        <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-sm text-gray-500">
          <span>{t('dateOfBirth')}: {formatDate(patient.dateOfBirth)}</span>
          <span>{t('ageGroup')}: {ageGroupLabel}</span>
          {patient.allergies.length > 0 && (
            <span className="text-amber-600">
              {t('allergiesCount', { count: patient.allergies.length })}
            </span>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={() => onView(patient.id!)}
        className="shrink-0 text-sm text-blue-600 hover:underline font-medium"
      >
        {t('viewRecord')}
      </button>
    </div>
  );
}

// ─── Creation modal ───────────────────────────────────────────────────────────

function CreatePatientModal({
  onClose,
  onCreated,
  t,
  tCommon,
}: {
  onClose: () => void;
  onCreated: (patient: PatientProfile) => void;
  t: ReturnType<typeof useTranslations<'patients'>>;
  tCommon: ReturnType<typeof useTranslations<'common'>>;
}) {
  const [form, setForm] = useState<CreateFormState>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  function set<K extends keyof CreateFormState>(key: K, value: CreateFormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const client = getApiClient();
      const allergies = form.allergies
        ? form.allergies.split(',').map((a) => a.trim()).filter(Boolean)
        : [];
      const medications = form.currentMedications
        ? form.currentMedications.split(',').map((m) => m.trim()).filter(Boolean)
        : [];
      const payload: Omit<PatientProfile, 'id'> = {
        fullName: form.fullName || undefined,
        dateOfBirth: form.dateOfBirth || undefined,
        weightKg: form.weightKg ? parseFloat(form.weightKg) : undefined,
        allergies,
        renalFailure: form.renalFailure,
        hepaticFailure: form.hepaticFailure,
        currentMedications: medications,
      };
      const created = await client.patients.createPatient(payload);
      onCreated(created);
    } catch {
      setError(t('errorCreate'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 id="modal-title" className="text-lg font-bold">{t('createTitle')}</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
            aria-label={tCommon('cancel')}
          >
            ✕
          </button>
        </div>

        <form onSubmit={(e) => void handleSubmit(e)} className="px-6 py-4 space-y-4">
          {/* Full name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('name')} <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              required
              value={form.fullName}
              onChange={(e) => set('fullName', e.target.value)}
              className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Date of birth + weight */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('dateOfBirth')}</label>
              <input
                type="date"
                value={form.dateOfBirth}
                onChange={(e) => set('dateOfBirth', e.target.value)}
                className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('weight')}</label>
              <input
                type="number"
                min={0}
                step={0.1}
                value={form.weightKg}
                onChange={(e) => set('weightKg', e.target.value)}
                className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Allergies */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('allergies')}</label>
            <input
              type="text"
              value={form.allergies}
              onChange={(e) => set('allergies', e.target.value)}
              placeholder={t('allergiesPlaceholder')}
              className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Current medications */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('medications')}</label>
            <input
              type="text"
              value={form.currentMedications}
              onChange={(e) => set('currentMedications', e.target.value)}
              placeholder={t('medicationsPlaceholder')}
              className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Comorbidities */}
          <fieldset>
            <legend className="text-sm font-medium text-gray-700 mb-2">{t('comorbidities')}</legend>
            <div className="flex gap-6">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.renalFailure}
                  onChange={(e) => set('renalFailure', e.target.checked)}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                {t('renalFailure')}
              </label>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.hepaticFailure}
                  onChange={(e) => set('hepaticFailure', e.target.checked)}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                {t('hepaticFailure')}
              </label>
            </div>
          </fieldset>

          {/* Error */}
          {error && (
            <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
              {error}
            </p>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm border rounded hover:bg-gray-50 transition-colors"
            >
              {tCommon('cancel')}
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? tCommon('loading') : tCommon('save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function PatientsPage() {
  const t = useTranslations('patients');
  const tCommon = useTranslations('common');
  const { user, isLoading: authLoading } = useAuth();
  const router = useRouter();

  const [patients, setPatients] = useState<PatientProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showModal, setShowModal] = useState(false);

  // Auth guard
  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login');
    }
  }, [authLoading, user, router]);

  const fetchPatients = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const client = getApiClient();
      const list = await client.patients.listPatients();
      setPatients(list);
    } catch {
      setError(t('errorFetch'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (user) {
      void fetchPatients();
    }
  }, [user, fetchPatients]);

  function handlePatientCreated(patient: PatientProfile) {
    setPatients((prev) => [patient, ...prev]);
    setShowModal(false);
  }

  function handleViewPatient(id: string) {
    router.push(`/patients/${id}`);
  }

  if (authLoading) {
    return (
      <main className="min-h-screen p-8 flex items-center justify-center">
        <p className="text-gray-500">{tCommon('loading')}</p>
      </main>
    );
  }

  if (!user) return null;

  return (
    <main className="min-h-screen p-8 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">{t('title')}</h1>
        <button
          type="button"
          onClick={() => setShowModal(true)}
          className="bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          + {t('new')}
        </button>
      </div>

      {/* Loading */}
      {loading && (
        <p className="text-gray-500 text-sm">{t('loading')}</p>
      )}

      {/* Error */}
      {error && (
        <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2 mb-4">
          {error}
        </p>
      )}

      {/* Patient list */}
      {!loading && !error && (
        patients.length === 0 ? (
          <p className="text-gray-500 text-sm">{t('noPatients')}</p>
        ) : (
          <div className="space-y-3">
            {patients.map((p) => (
              <PatientCard
                key={p.id}
                patient={p}
                onView={handleViewPatient}
                t={t}
              />
            ))}
          </div>
        )
      )}

      {/* Creation modal */}
      {showModal && (
        <CreatePatientModal
          onClose={() => setShowModal(false)}
          onCreated={handlePatientCreated}
          t={t}
          tCommon={tCommon}
        />
      )}
    </main>
  );
}
