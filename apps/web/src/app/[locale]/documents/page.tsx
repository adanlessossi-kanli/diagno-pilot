'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { createApiClient } from '@diagno-pilot/api-client';
import type { PatientDocument } from '@diagno-pilot/api-client';
import { useAuth } from '../../../contexts/AuthContext';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('fr-FR');
}

// ─── Constants ────────────────────────────────────────────────────────────────

const SOURCES = ['CHU_LOME', 'CHU_ABOMEY_CALAVI', 'OMS_AFRO', 'MSF', 'PNLP'] as const;
type DocumentSource = (typeof SOURCES)[number];

const ACCEPTED_FORMATS = '.pdf,.docx,.txt,.csv';

// ─── Upload form state ────────────────────────────────────────────────────────

interface UploadFormState {
  title: string;
  source: DocumentSource | '';
  file: File | null;
}

const EMPTY_UPLOAD: UploadFormState = {
  title: '',
  source: '',
  file: null,
};

// ─── Document row ─────────────────────────────────────────────────────────────

function DocumentRow({
  doc,
  onDelete,
  t,
  tCommon,
}: {
  doc: PatientDocument;
  onDelete: (id: string) => void;
  t: ReturnType<typeof useTranslations<'admin'>>;
  tCommon: ReturnType<typeof useTranslations<'common'>>;
}) {
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!window.confirm(t('confirmDelete'))) return;
    setDeleting(true);
    onDelete(doc.id);
  }

  const sourceLabel = SOURCES.includes(doc.source as DocumentSource)
    ? t(`sources.${doc.source as DocumentSource}`)
    : doc.source;

  return (
    <tr className="border-b last:border-0 hover:bg-gray-50 transition-colors">
      <td className="px-4 py-3 text-sm font-medium text-gray-900 max-w-xs truncate">
        {doc.title || '—'}
      </td>
      <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">
        {sourceLabel}
      </td>
      <td className="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">
        {formatDate(doc.indexedAt ?? doc.createdAt)}
      </td>
      <td className="px-4 py-3 text-sm text-gray-500 text-right">
        {doc.chunkCount != null && doc.chunkCount > 0 ? doc.chunkCount : (doc.sizeBytes ? `${Math.round(doc.sizeBytes / 1024)} KB` : '—')}
      </td>
      <td className="px-4 py-3 text-sm">
        <button
          type="button"
          onClick={() => void handleDelete()}
          disabled={deleting}
          className="text-red-600 hover:text-red-800 font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          aria-label={`${tCommon('delete')} ${doc.title}`}
        >
          {deleting ? '…' : tCommon('delete')}
        </button>
      </td>
    </tr>
  );
}

// ─── Upload form ──────────────────────────────────────────────────────────────

function UploadForm({
  onUploaded,
  t,
  tCommon,
  apiClient,
}: {
  onUploaded: (doc: PatientDocument) => void;
  t: ReturnType<typeof useTranslations<'admin'>>;
  tCommon: ReturnType<typeof useTranslations<'common'>>;
  apiClient: ReturnType<typeof createApiClient>;
}) {
  const [form, setForm] = useState<UploadFormState>(EMPTY_UPLOAD);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  function set<K extends keyof UploadFormState>(key: K, value: UploadFormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setError('');
    setSuccess('');
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.file) return;
    setError('');
    setSuccess('');
    setSubmitting(true);
    try {
      const result = await apiClient.documents.uploadDocument(form.file, {
        title: form.title || undefined,
        source: form.source || undefined,
      });
      // Build a minimal PatientDocument from the upload response for optimistic UI
      const newDoc: PatientDocument = {
        id: result.id,
        title: result.title,
        source: form.source || '',
        s3Key: '',
        originalName: form.file.name,
        sizeBytes: form.file.size,
        indexedAt: result.createdAt,
        createdAt: result.createdAt,
      };
      onUploaded(newDoc);
      setForm(EMPTY_UPLOAD);
      setSuccess(t('uploadSuccess'));
    } catch {
      setError(t('errorUpload'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="border rounded-lg p-6 bg-white">
      <h2 className="text-lg font-semibold mb-4">{t('uploadTitle')}</h2>

      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
        {/* Title */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('documentTitle')}
          </label>
          <input
            type="text"
            value={form.title}
            onChange={(e) => set('title', e.target.value)}
            placeholder={t('documentTitlePlaceholder')}
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Source */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('documentSource')}
          </label>
          <select
            value={form.source}
            onChange={(e) => set('source', e.target.value as DocumentSource | '')}
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">— {t('selectSource')} —</option>
            {SOURCES.map((src) => (
              <option key={src} value={src}>
                {t(`sources.${src}`)}
              </option>
            ))}
          </select>
        </div>

        {/* File */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('documentFile')} <span className="text-red-500">*</span>
          </label>
          <input
            type="file"
            required
            accept={ACCEPTED_FORMATS}
            onChange={(e) => set('file', e.target.files?.[0] ?? null)}
            className="w-full text-sm text-gray-600 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border file:border-gray-300 file:text-sm file:font-medium file:bg-gray-50 file:text-gray-700 hover:file:bg-gray-100 cursor-pointer"
          />
        </div>

        {/* Feedback */}
        {error && (
          <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {error}
          </p>
        )}
        {success && (
          <p role="status" className="text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2">
            {success}
          </p>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={submitting || !form.file}
          className="bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? t('uploading') : t('upload')}
        </button>
      </form>
    </section>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function DocumentsPage() {
  const t = useTranslations('admin');
  const tCommon = useTranslations('common');
  const { user, isLoading: authLoading } = useAuth();
  const router = useRouter();

  const apiClient = useMemo(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
    return createApiClient(baseUrl);
  }, []);

  const [documents, setDocuments] = useState<PatientDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState('');
  const [deleteError, setDeleteError] = useState('');

  // Auth guard — redirect unauthenticated users only
  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login');
    }
  }, [authLoading, user, router]);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setFetchError('');
    try {
      const list = await apiClient.documents.listDocuments();
      setDocuments(list);
    } catch {
      setFetchError(t('errorFetch'));
    } finally {
      setLoading(false);
    }
  }, [t, apiClient]);

  useEffect(() => {
    if (user) {
      void fetchDocuments();
    }
  }, [user, fetchDocuments]);

  async function handleDelete(id: string) {
    setDeleteError('');
    try {
      await apiClient.documents.deleteDocument(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
    } catch {
      setDeleteError(t('errorDelete'));
    }
  }

  function handleUploaded(doc: PatientDocument) {
    setDocuments((prev) => [doc, ...prev]);
  }

  // Loading auth
  if (authLoading) {
    return (
      <main className="min-h-screen p-8 flex items-center justify-center">
        <p className="text-gray-500">{tCommon('loading')}</p>
      </main>
    );
  }

  // Not authenticated — render nothing while redirect fires
  if (!user) {
    return null;
  }

  return (
    <main className="min-h-screen p-8 max-w-5xl mx-auto space-y-8">
      <h1 className="text-2xl font-bold">{t('title')}</h1>

      {/* Upload form */}
      <UploadForm onUploaded={handleUploaded} t={t} tCommon={tCommon} apiClient={apiClient} />

      {/* Document list */}
      <section className="border rounded-lg bg-white overflow-hidden">
        <div className="px-6 py-4 border-b">
          <h2 className="text-lg font-semibold">{t('documents')}</h2>
        </div>

        {/* Delete error */}
        {deleteError && (
          <div className="px-6 py-3">
            <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
              {deleteError}
            </p>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <p className="px-6 py-4 text-sm text-gray-500">{t('loadingDocuments')}</p>
        )}

        {/* Fetch error */}
        {!loading && fetchError && (
          <p role="alert" className="px-6 py-4 text-sm text-red-600">
            {fetchError}
          </p>
        )}

        {/* Empty state */}
        {!loading && !fetchError && documents.length === 0 && (
          <p className="px-6 py-4 text-sm text-gray-500">{t('noDocuments')}</p>
        )}

        {/* Table */}
        {!loading && !fetchError && documents.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-700">{t('columnTitle')}</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-700">{t('columnSource')}</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-700">{t('columnDate')}</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-700">{t('columnChunks')}</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-700">{t('columnActions')}</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => (
                  <DocumentRow
                    key={doc.id}
                    doc={doc}
                    onDelete={(id) => void handleDelete(id)}
                    t={t}
                    tCommon={tCommon}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
