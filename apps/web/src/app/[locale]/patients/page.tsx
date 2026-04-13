'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslations, useLocale } from 'next-intl';
import { useRouter, useSearchParams } from 'next/navigation';
import { createApiClient } from '@diagno-pilot/api-client';
import type { PatientProfile } from '@diagno-pilot/types';
import { useAuth } from '../../../contexts/AuthContext';
import Pagination from '../../../components/Pagination';
import { Toast } from '../../../components/Toast';
import SkeletonLoader from '../../../components/SkeletonLoader';
import EmptyState from '../../../components/EmptyState';
import { ConfirmDialog } from '../../../components/ConfirmDialog';
import { IMAGES } from '@/lib/images';
import { buttonVariants } from '@diagno-pilot/ui';
import BackToTop from '../../../components/BackToTop';
import { buildErrorMessage } from '../../../utils/errorMessages';
import { useRequestTimeout } from '../../../hooks/useRequestTimeout';
import { filterPatientsByName } from '../../../utils/filterPatients';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('fr-FR');
}

const PAGE_SIZE = 20;

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

// ─── Zod schema ───────────────────────────────────────────────────────────────

function createPatientSchema(t: ReturnType<typeof useTranslations<'patients'>>) {
  return z.object({
    fullName: z.string().min(1, t('nameRequired')),
    dateOfBirth: z.string().optional(),
    weightKg: z
      .string()
      .optional()
      .refine(
        (val) => !val || parseFloat(val) > 0,
        { message: t('weightPositive') }
      ),
    allergies: z.string().optional(),
    renalFailure: z.boolean(),
    hepaticFailure: z.boolean(),
    currentMedications: z.string().optional(),
  });
}

type CreatePatientFormValues = z.infer<ReturnType<typeof createPatientSchema>>;

const EMPTY_FORM: CreatePatientFormValues = {
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
    <div className="border rounded-lg shadow-sm p-4 bg-white hover:shadow-md transition-shadow duration-200 flex items-center justify-between gap-4">
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
  const locale = useLocale();
  const apiClient = useMemo(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
    return createApiClient(baseUrl, undefined, () => locale);
  }, [locale]);
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState('');
  const [showSuccessToast, setShowSuccessToast] = useState(false);
  const [showUnsavedDialog, setShowUnsavedDialog] = useState(false);

  const schema = useMemo(() => createPatientSchema(t), [t]);

  const {
    register,
    handleSubmit,
    formState: { errors, isDirty },
  } = useForm<CreatePatientFormValues>({
    resolver: zodResolver(schema),
    mode: 'onChange',
    defaultValues: EMPTY_FORM,
  });

  function handleClose() {
    if (isDirty && !submitting) {
      setShowUnsavedDialog(true);
    } else {
      onClose();
    }
  }

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && !submitting) {
        e.preventDefault();
        if (isDirty) {
          setShowUnsavedDialog(true);
        } else {
          onClose();
        }
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isDirty, submitting, onClose]);

  async function onSubmit(data: CreatePatientFormValues) {
    setApiError('');
    setSubmitting(true);
    try {
      const allergies = data.allergies
        ? data.allergies.split(',').map((a) => a.trim()).filter(Boolean)
        : [];
      const medications = data.currentMedications
        ? data.currentMedications.split(',').map((m) => m.trim()).filter(Boolean)
        : [];
      const payload: Omit<PatientProfile, 'id'> = {
        fullName: data.fullName || undefined,
        dateOfBirth: data.dateOfBirth || undefined,
        weightKg: data.weightKg ? parseFloat(data.weightKg) : undefined,
        allergies,
        renalFailure: data.renalFailure,
        hepaticFailure: data.hepaticFailure,
        currentMedications: medications,
      };
      const created = await apiClient.patients.createPatient(payload);
      setShowSuccessToast(true);
      // Wait at least 2 seconds before closing (REQ 9.5)
      setTimeout(() => {
        onCreated(created);
      }, 2000);
    } catch {
      setApiError(t('errorCreate'));
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
      onClick={handleClose}
    >
      {showSuccessToast && (
        <Toast
          message={t('successCreate')}
          type="success"
          duration={2000}
        />
      )}

      <div className="relative bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        {submitting && (
          <div className="absolute inset-0 bg-white/60 flex items-center justify-center rounded-xl z-10" data-testid="spinner-overlay">
            <svg className="animate-spin h-8 w-8 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          </div>
        )}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 id="modal-title" className="text-lg font-bold">{t('createTitle')}</h2>
          <button
            type="button"
            onClick={handleClose}
            disabled={submitting}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label={tCommon('cancel')}
          >
            ✕
          </button>
        </div>

        <form onSubmit={(e) => void handleSubmit(onSubmit)(e)} className="px-6 py-4 space-y-4">
          {/* Full name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('name')} <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              {...register('fullName')}
              autoFocus
              disabled={submitting}
              className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            {errors.fullName && (
              <p role="alert" className="text-xs text-red-600 mt-1">{errors.fullName.message}</p>
            )}
          </div>

          {/* Date of birth + weight */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('dateOfBirth')}</label>
              <input
                type="date"
                {...register('dateOfBirth')}
                disabled={submitting}
                className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{t('weight')}</label>
              <input
                type="number"
                min={0}
                step={0.1}
                {...register('weightKg')}
                disabled={submitting}
                className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              />
              {errors.weightKg && (
                <p role="alert" className="text-xs text-red-600 mt-1">{errors.weightKg.message}</p>
              )}
            </div>
          </div>

          {/* Allergies */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('allergies')}</label>
            <input
              type="text"
              {...register('allergies')}
              placeholder={t('allergiesPlaceholder')}
              disabled={submitting}
              className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>

          {/* Current medications */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('medications')}</label>
            <input
              type="text"
              {...register('currentMedications')}
              placeholder={t('medicationsPlaceholder')}
              disabled={submitting}
              className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>

          {/* Comorbidities */}
          <fieldset>
            <legend className="text-sm font-medium text-gray-700 mb-2">{t('comorbidities')}</legend>
            <div className="flex gap-6">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  {...register('renalFailure')}
                  disabled={submitting}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                />
                {t('renalFailure')}
              </label>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  {...register('hepaticFailure')}
                  disabled={submitting}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                />
                {t('hepaticFailure')}
              </label>
            </div>
          </fieldset>

          {/* API Error */}
          {apiError && (
            <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
              {apiError}
            </p>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={handleClose}
              disabled={submitting}
              className={buttonVariants.secondary}
            >
              {tCommon('cancel')}
            </button>
            <button
              type="submit"
              disabled={submitting}
              className={`${buttonVariants.primary} flex items-center gap-2`}
            >
              {submitting && (
                <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
              )}
              {submitting ? tCommon('loading') : tCommon('save')}
            </button>
          </div>
        </form>
      </div>

      <ConfirmDialog
        open={showUnsavedDialog}
        title={t('unsavedChanges')}
        message={t('unsavedChangesMessage')}
        confirmLabel={tCommon('confirm')}
        cancelLabel={tCommon('cancel')}
        onConfirm={() => {
          setShowUnsavedDialog(false);
          onClose();
        }}
        onCancel={() => setShowUnsavedDialog(false)}
      />
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function PatientsPage() {
  const t = useTranslations('patients');
  const tCommon = useTranslations('common');
  const tErrors = useTranslations('errors');
  const { user, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const locale = useLocale();
  const { startTimer, clearTimer, isWarning, isAborted } = useRequestTimeout();

  const apiClient = useMemo(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
    return createApiClient(baseUrl, undefined, () => locale);
  }, [locale]);

  // Lire la page courante depuis le query param URL (?page=N)
  const currentPage = Math.max(1, parseInt(searchParams.get('page') ?? '1', 10) || 1);

  const [patients, setPatients] = useState<PatientProfile[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const filteredPatients = useMemo(
    () => filterPatientsByName(patients, searchQuery),
    [patients, searchQuery]
  );

  // Auth guard
  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login');
    }
  }, [authLoading, user, router]);

  const fetchPatients = useCallback(async (page: number) => {
    setLoading(true);
    setError('');
    const controller = new AbortController();
    startTimer(controller);
    try {
      const result = await apiClient.patients.listPatients(page, PAGE_SIZE);
      setPatients(result.items);
      setTotal(result.total);
    } catch {
      const { descriptionKey, actionKey } = buildErrorMessage('network');
      const descKey = descriptionKey.replace('errors.', '') as Parameters<typeof tErrors>[0];
      const actKey = actionKey.replace('errors.', '') as Parameters<typeof tErrors>[0];
      setError(`${tErrors(descKey)} ${tErrors(actKey)}`);
    } finally {
      clearTimer();
      setLoading(false);
    }
  }, [apiClient, tErrors, startTimer, clearTimer]);

  useEffect(() => {
    if (user) {
      void fetchPatients(currentPage);
    }
  }, [user, fetchPatients, currentPage]);

  function handlePatientCreated(patient: PatientProfile) {
    // Après création, recharger la page courante pour inclure le nouveau patient
    setPatients((prev) => [patient, ...prev]);
    setTotal((prev) => prev + 1);
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
        <div className="flex items-center gap-3">
          {user.role === 'medecin' && (
            <a
              href={`/${locale}/create-nurse`}
              className={buttonVariants.secondary}
            >
              + {t('createNurse')}
            </a>
          )}
          <button
            type="button"
            onClick={() => setShowModal(true)}
            className={buttonVariants.primary}
          >
            + {t('new')}
          </button>
        </div>
      </div>

      {/* Search */}
      {!loading && patients.length > 0 && (
        <div className="mb-4">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('search')}
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label={t('search')}
          />
        </div>
      )}

      {/* Loading */}
      {loading && (
        <SkeletonLoader count={5} />
      )}

      {/* Error */}
      {error && (
        <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2 mb-4">
          {error}
        </p>
      )}

      {/* Timeout warning */}
      {isWarning && !isAborted && (
        <p role="status" className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 mb-4">
          {tErrors('timeout')} {tErrors('timeoutAction')}
        </p>
      )}

      {/* Auto-cancel notice */}
      {isAborted && (
        <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2 mb-4">
          {tErrors('autoCancel')}
        </p>
      )}

      {/* Patient list */}
      {!loading && !error && (
        patients.length === 0 ? (
          <EmptyState
            title={t('noPatients')}
            description={t('emptyDescription')}
            action={{ label: t('new'), onClick: () => setShowModal(true) }}
            image={IMAGES.patientsEmpty}
          />
        ) : filteredPatients.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-8">{tCommon('noResults')}</p>
        ) : (
          <>
            <div className="space-y-3">
              {filteredPatients.map((p) => (
                <PatientCard
                  key={p.id}
                  patient={p}
                  onView={handleViewPatient}
                  t={t}
                />
              ))}
            </div>
            <Pagination
              page={currentPage}
              pageSize={PAGE_SIZE}
              total={total}
            />
          </>
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
      <BackToTop />
    </main>
  );
}
