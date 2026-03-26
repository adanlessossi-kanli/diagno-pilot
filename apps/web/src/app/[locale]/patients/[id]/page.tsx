'use client';

import { useState, useEffect, useCallback, use, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { createApiClient } from '@diagno-pilot/api-client';
import type { PatientFile, UploadFileResponse } from '@diagno-pilot/api-client';
import type { PatientProfile, Consultation } from '@diagno-pilot/types';
import { useAuth } from '../../../../contexts/AuthContext';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('fr-FR');
}

function formatPercent(p: number): string {
  return `${Math.round(p * 100)}%`;
}

// ─── Consultation card ────────────────────────────────────────────────────────

function ConsultationCard({
  consultation,
  t,
}: {
  consultation: Consultation;
  t: ReturnType<typeof useTranslations<'patientDetail'>>;
}) {
  const [expanded, setExpanded] = useState(false);
  const topDiag = consultation.diagnoses[0];
  const rx = consultation.prescription;

  return (
    <div className="border rounded-lg bg-white overflow-hidden">
      {/* Summary row */}
      <div className="p-4 flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-xs text-gray-400">{formatDate(consultation.createdAt)}</p>

          {/* Symptoms */}
          {consultation.symptoms.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {consultation.symptoms.map((s, i) => (
                <span key={i} className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded">
                  {s.name}
                </span>
              ))}
            </div>
          )}

          {/* Top diagnosis */}
          {topDiag && (
            <p className="text-sm font-medium text-gray-800 mt-1">
              {topDiag.condition}
              <span className="ml-2 text-xs font-normal text-gray-500">
                ({formatPercent(topDiag.probability)})
              </span>
            </p>
          )}

          {/* Prescription summary */}
          {rx && (
            <p className="text-xs text-gray-500">
              {rx.antibiotic} — {rx.dose_mg} mg — {rx.frequency} — {rx.duration_days}j
            </p>
          )}
        </div>

        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="shrink-0 text-xs text-blue-600 hover:underline"
        >
          {expanded ? t('collapse') : t('expand')}
        </button>
      </div>

      {/* Expanded detail (read-only) */}
      {expanded && (
        <div className="border-t bg-gray-50 px-4 py-4 space-y-4 text-sm">
          {/* All symptoms */}
          {consultation.symptoms.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase mb-1">{t('symptoms')}</p>
              <ul className="space-y-0.5">
                {consultation.symptoms.map((s, i) => (
                  <li key={i} className="text-gray-700">
                    {s.name}
                    <span className="text-gray-400 ml-1">— {s.severity}, {s.duration_days}j</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* All diagnoses */}
          {consultation.diagnoses.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase mb-1">{t('topDiagnosis')}</p>
              <ul className="space-y-1">
                {consultation.diagnoses.map((d, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <span className="text-gray-800">{d.condition}</span>
                    {d.icd_code && (
                      <span className="text-xs font-mono bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded">
                        {d.icd_code}
                      </span>
                    )}
                    <span className="text-xs text-gray-400 ml-auto">{formatPercent(d.probability)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Prescription */}
          {rx && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase mb-1">{t('prescription')}</p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-gray-700">
                <span className="text-gray-500">{t('antibiotic')}</span>
                <span>{rx.antibiotic}</span>
                <span className="text-gray-500">{t('dose')}</span>
                <span>
                  {rx.dose_mg} mg
                  {rx.dose_per_kg ? ` (${rx.dose_per_kg} mg/kg)` : ''}
                </span>
                <span className="text-gray-500">{t('frequency')}</span>
                <span>{rx.frequency}</span>
                <span className="text-gray-500">{t('duration')}</span>
                <span>{t('durationDays', { days: rx.duration_days })}</span>
                <span className="text-gray-500">{t('route')}</span>
                <span>{rx.route}</span>
              </div>
            </div>
          )}

          {/* LLM used */}
          {consultation.llmUsed && (
            <p className="text-xs text-gray-400">{t('llmUsed')}: {consultation.llmUsed}</p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── File row ─────────────────────────────────────────────────────────────────

function FileRow({
  file,
  apiClient,
  t,
}: {
  file: PatientFile;
  apiClient: ReturnType<typeof createApiClient>;
  t: ReturnType<typeof useTranslations<'patientDetail'>>;
}) {
  const [downloading, setDownloading] = useState(false);
  const [dlError, setDlError] = useState('');

  async function handleDownload() {
    setDlError('');
    setDownloading(true);
    try {
      const { url } = await apiClient.files.getFileUrl(file.id);
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch {
      setDlError(t('errorDownload'));
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="flex items-center justify-between gap-4 py-2 border-b last:border-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-gray-800 truncate">{file.originalName}</p>
        <p className="text-xs text-gray-400">
          {file.fileType} · {formatDate(file.createdAt)}
        </p>
        {dlError && <p className="text-xs text-red-500 mt-0.5">{dlError}</p>}
      </div>
      <button
        type="button"
        onClick={() => void handleDownload()}
        disabled={downloading}
        className="shrink-0 text-xs text-blue-600 hover:underline disabled:opacity-50"
      >
        {downloading ? '...' : t('download')}
      </button>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

interface PatientDetailPageProps {
  params: Promise<{ locale: string; id: string }>;
}

export default function PatientDetailPage({ params }: PatientDetailPageProps) {
  const { id } = use(params);
  const t = useTranslations('patientDetail');
  const tCommon = useTranslations('common');
  const { user, isLoading: authLoading, getToken } = useAuth();
  const router = useRouter();

  const apiClient = useMemo(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
    return createApiClient(baseUrl, getToken);
  }, [getToken]);

  const [patient, setPatient] = useState<PatientProfile | null>(null);
  const [consultations, setConsultations] = useState<Consultation[]>([]);
  const [files, setFiles] = useState<PatientFile[]>([]);

  const [loadingPatient, setLoadingPatient] = useState(true);
  const [loadingConsultations, setLoadingConsultations] = useState(true);
  const [loadingFiles, setLoadingFiles] = useState(true);

  const [errorPatient, setErrorPatient] = useState('');
  const [errorConsultations, setErrorConsultations] = useState('');
  const [errorFiles, setErrorFiles] = useState('');

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [uploadSuccess, setUploadSuccess] = useState(false);

  // Auth guard
  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login');
    }
  }, [authLoading, user, router]);

  // Fetch patient
  const fetchPatient = useCallback(async () => {
    setLoadingPatient(true);
    setErrorPatient('');
    try {
      const p = await apiClient.patients.getPatient(id);
      setPatient(p);
    } catch {
      setErrorPatient(t('errorFetch'));
    } finally {
      setLoadingPatient(false);
    }
  }, [id, t, apiClient]);

  // Fetch consultations
  const fetchConsultations = useCallback(async () => {
    setLoadingConsultations(true);
    setErrorConsultations('');
    try {
      const list = await apiClient.patients.listConsultations(id);
      setConsultations(list);
    } catch {
      setErrorConsultations(t('errorFetchConsultations'));
    } finally {
      setLoadingConsultations(false);
    }
  }, [id, t, apiClient]);

  // Fetch files — call the files endpoint directly since api-client doesn't have listFiles
  const fetchFiles = useCallback(async () => {
    setLoadingFiles(true);
    setErrorFiles('');
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
      const token = getToken();
      const res = await fetch(
        `${baseUrl}/api/v1/files?patient_id=${encodeURIComponent(id)}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} },
      );
      if (!res.ok) throw new Error('fetch failed');
      const data = (await res.json()) as PatientFile[];
      setFiles(data);
    } catch {
      setErrorFiles(t('errorFetchFiles'));
    } finally {
      setLoadingFiles(false);
    }
  }, [id, t, getToken]);

  useEffect(() => {
    if (user) {
      void fetchPatient();
      void fetchConsultations();
      void fetchFiles();
    }
  }, [user, fetchPatient, fetchConsultations, fetchFiles]);

  // File upload handler
  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadError('');
    setUploadSuccess(false);
    setUploading(true);

    try {
      await apiClient.files.uploadFile(file, id);
      setUploadSuccess(true);
      // Reset input
      e.target.value = '';
      // Refresh file list
      await fetchFiles();
    } catch {
      setUploadError(t('errorUpload'));
    } finally {
      setUploading(false);
    }
  }

  if (authLoading || loadingPatient) {
    return (
      <main className="min-h-screen p-8 flex items-center justify-center">
        <p className="text-gray-500">{tCommon('loading')}</p>
      </main>
    );
  }

  if (!user) return null;

  return (
    <main className="min-h-screen p-8 max-w-5xl mx-auto">
      {/* Back button */}
      <button
        type="button"
        onClick={() => router.back()}
        className="text-sm text-blue-600 hover:underline mb-6 inline-block"
      >
        {t('back')}
      </button>

      {/* Patient fetch error */}
      {errorPatient && (
        <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2 mb-4">
          {errorPatient}
        </p>
      )}

      {patient && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* ── Left column: patient info + files ── */}
          <aside className="md:col-span-1 space-y-6">
            {/* Patient header */}
            <section className="border rounded-lg p-4 bg-white space-y-3">
              <h1 className="text-xl font-bold text-gray-900">{patient.fullName ?? '—'}</h1>

              <dl className="space-y-1.5 text-sm">
                <div className="flex justify-between gap-2">
                  <dt className="text-gray-500">{t('dateOfBirth')}</dt>
                  <dd className="text-gray-800">{formatDate(patient.dateOfBirth)}</dd>
                </div>
                {patient.ageGroup && (
                  <div className="flex justify-between gap-2">
                    <dt className="text-gray-500">{t('ageGroup')}</dt>
                    <dd className="text-gray-800">
                      {t(`ageGroups.${patient.ageGroup}` as Parameters<typeof t>[0])}
                    </dd>
                  </div>
                )}
                {patient.weightKg != null && (
                  <div className="flex justify-between gap-2">
                    <dt className="text-gray-500">{t('weight')}</dt>
                    <dd className="text-gray-800">{t('weightKg', { weight: patient.weightKg })}</dd>
                  </div>
                )}
              </dl>

              {/* Allergies */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase mb-1">{t('allergies')}</p>
                {patient.allergies.length === 0 ? (
                  <p className="text-sm text-gray-400">{t('noAllergies')}</p>
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {patient.allergies.map((a, i) => (
                      <span key={i} className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded">
                        {a}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Comorbidities */}
              {(patient.renalFailure || patient.hepaticFailure) && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-1">{t('comorbidities')}</p>
                  <div className="flex flex-wrap gap-1">
                    {patient.renalFailure && (
                      <span className="text-xs bg-red-50 text-red-700 border border-red-200 px-2 py-0.5 rounded">
                        {t('renalFailure')}
                      </span>
                    )}
                    {patient.hepaticFailure && (
                      <span className="text-xs bg-red-50 text-red-700 border border-red-200 px-2 py-0.5 rounded">
                        {t('hepaticFailure')}
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Current medications */}
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase mb-1">{t('medications')}</p>
                {patient.currentMedications.length === 0 ? (
                  <p className="text-sm text-gray-400">{t('noMedications')}</p>
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {patient.currentMedications.map((m, i) => (
                      <span key={i} className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded">
                        {m}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </section>

            {/* ── Clinical files ── */}
            <section className="border rounded-lg p-4 bg-white space-y-3">
              <h2 className="font-semibold text-gray-900">{t('files')}</h2>

              {/* Upload */}
              <div>
                <label
                  htmlFor="file-upload"
                  className={`inline-block cursor-pointer text-sm px-3 py-1.5 rounded border transition-colors ${
                    uploading
                      ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
                      : 'bg-blue-600 text-white border-blue-600 hover:bg-blue-700'
                  }`}
                >
                  {uploading ? t('uploading') : t('uploadFile')}
                </label>
                <input
                  id="file-upload"
                  type="file"
                  accept=".pdf,.docx,.csv,.png,.jpg,.jpeg,.gif,.bmp,.tiff"
                  disabled={uploading}
                  onChange={(e) => void handleFileChange(e)}
                  className="sr-only"
                />
              </div>

              {uploadSuccess && (
                <p className="text-xs text-green-600">{t('uploadSuccess')}</p>
              )}
              {uploadError && (
                <p className="text-xs text-red-600">{uploadError}</p>
              )}

              {/* File list */}
              {loadingFiles && (
                <p className="text-sm text-gray-400">{t('loadingFiles')}</p>
              )}
              {errorFiles && (
                <p className="text-sm text-red-500">{errorFiles}</p>
              )}
              {!loadingFiles && !errorFiles && files.length === 0 && (
                <p className="text-sm text-gray-400">{t('noFiles')}</p>
              )}
              {!loadingFiles && files.length > 0 && (
                <div>
                  {files.map((f) => (
                    <FileRow key={f.id} file={f} apiClient={apiClient} t={t} />
                  ))}
                </div>
              )}
            </section>
          </aside>

          {/* ── Right column: consultation history ── */}
          <section className="md:col-span-2 space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">{t('consultations')}</h2>

            {loadingConsultations && (
              <p className="text-sm text-gray-400">{t('loadingConsultations')}</p>
            )}
            {errorConsultations && (
              <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
                {errorConsultations}
              </p>
            )}
            {!loadingConsultations && !errorConsultations && consultations.length === 0 && (
              <p className="text-sm text-gray-400">{t('noConsultations')}</p>
            )}
            {!loadingConsultations && consultations.length > 0 && (
              <div className="space-y-3">
                {consultations.map((c) => (
                  <ConsultationCard key={c.id} consultation={c} t={t} />
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
