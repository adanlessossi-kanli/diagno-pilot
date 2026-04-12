'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import type { createApiClient } from '@diagno-pilot/api-client';
import type { PatientDocument } from '@diagno-pilot/api-client';

// ─── Constants ────────────────────────────────────────────────────────────────

const SOURCES = ['CHU_LOME', 'CHU_ABOMEY_CALAVI', 'OMS_AFRO', 'MSF', 'PNLP'] as const;
type SourceValue = (typeof SOURCES)[number];

const ACCEPTED_FORMATS = '.pdf,.docx,.txt,.csv';

/**
 * Validate that a filename has an accepted extension.
 * Accepted: pdf, docx, txt, csv (case-insensitive). NOT html.
 */
export function isAcceptedFileFormat(filename: string): boolean {
  const ext = filename.split('.').pop()?.toLowerCase() ?? '';
  return ['pdf', 'docx', 'txt', 'csv'].includes(ext);
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('fr-FR');
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface UploadFormState {
  title: string;
  source: SourceValue | '';
  file: File | null;
}

const EMPTY_UPLOAD: UploadFormState = { title: '', source: '', file: null };

export interface DocumentSidebarProps {
  apiClient: ReturnType<typeof createApiClient>;
  userRole: string;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function DocumentSidebar({ apiClient, userRole }: DocumentSidebarProps) {
  const t = useTranslations('documentSidebar');
  const tAdmin = useTranslations('admin');

  // ── State ─────────────────────────────────────────────────────────────────
  const [documents, setDocuments] = useState<PatientDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState('');
  const [deleteError, setDeleteError] = useState('');

  // Upload form
  const [form, setForm] = useState<UploadFormState>(EMPTY_UPLOAD);
  const [submitting, setSubmitting] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [uploadSuccess, setUploadSuccess] = useState('');
  const [elapsedSec, setElapsedSec] = useState(0);

  // Download errors keyed by document id
  const [downloadErrors, setDownloadErrors] = useState<Record<string, boolean>>({});

  // ── Fetch documents on mount ──────────────────────────────────────────────
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
  }, [apiClient, t]);

  useEffect(() => {
    void fetchDocuments();
  }, [fetchDocuments]);

  // ── Upload elapsed timer ──────────────────────────────────────────────────
  useEffect(() => {
    if (!submitting) {
      setElapsedSec(0);
      return;
    }
    const interval = setInterval(() => setElapsedSec((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, [submitting]);

  // ── Form helpers ──────────────────────────────────────────────────────────
  function setField<K extends keyof UploadFormState>(key: K, value: UploadFormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setUploadError('');
    setUploadSuccess('');
  }

  // ── Upload handler ────────────────────────────────────────────────────────
  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!form.file) return;

    if (!isAcceptedFileFormat(form.file.name)) {
      setUploadError(t('errorUpload'));
      return;
    }

    setUploadError('');
    setUploadSuccess('');
    setSubmitting(true);
    try {
      const result = await apiClient.documents.uploadDocument(form.file, {
        title: form.title || undefined,
        source: form.source || undefined,
      });
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
      setDocuments((prev) => [newDoc, ...prev]);
      setForm(EMPTY_UPLOAD);
      setUploadSuccess(t('uploadSuccess'));
    } catch {
      setUploadError(t('errorUpload'));
    } finally {
      setSubmitting(false);
    }
  }

  // ── Delete handler ────────────────────────────────────────────────────────
  async function handleDelete(id: string) {
    if (!window.confirm(t('confirmDelete'))) return;
    setDeleteError('');
    try {
      await apiClient.documents.deleteDocument(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
    } catch {
      setDeleteError(t('errorDelete'));
    }
  }

  // ── Download handler ──────────────────────────────────────────────────────
  async function handleDownload(documentId: string, fallbackFilename: string) {
    try {
      setDownloadErrors((prev) => ({ ...prev, [documentId]: false }));
      const { url, filename } = await apiClient.documents.getDownloadUrl(documentId);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || fallbackFilename;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch {
      setDownloadErrors((prev) => ({ ...prev, [documentId]: true }));
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <aside className="flex flex-col h-full border-l bg-white">
      {/* ── Upload Form ──────────────────────────────────────────────────── */}
      <section className="p-4 border-b">
        <h2 className="text-sm font-semibold mb-3">{t('uploadTitle')}</h2>

        <form onSubmit={(e) => void handleUpload(e)} className="space-y-3">
          {/* Title */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              {t('documentTitle')}
            </label>
            <input
              type="text"
              value={form.title}
              onChange={(e) => setField('title', e.target.value)}
              className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Source */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              {t('documentSource')}
            </label>
            <select
              value={form.source}
              onChange={(e) => setField('source', e.target.value as SourceValue | '')}
              className="w-full border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">— {t('selectSource')} —</option>
              {SOURCES.map((src) => (
                <option key={src} value={src}>
                  {tAdmin(`sources.${src}`)}
                </option>
              ))}
            </select>
          </div>

          {/* File */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              {t('documentFile')} <span className="text-red-500">*</span>
            </label>
            <input
              type="file"
              required
              accept={ACCEPTED_FORMATS}
              onChange={(e) => setField('file', e.target.files?.[0] ?? null)}
              className="w-full text-xs text-gray-600 file:mr-2 file:py-1 file:px-2 file:rounded file:border file:border-gray-300 file:text-xs file:font-medium file:bg-gray-50 file:text-gray-700 hover:file:bg-gray-100 cursor-pointer"
            />
          </div>

          {/* Progress indicator */}
          {submitting && (
            <div className="flex items-center gap-2 text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded px-3 py-2">
              <svg className="animate-spin h-4 w-4 text-blue-600 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              <span>{t('uploading')} ({elapsedSec}s)</span>
            </div>
          )}

          {/* Error / Success */}
          {uploadError && !submitting && (
            <p role="alert" className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1.5">
              {uploadError}
            </p>
          )}
          {uploadSuccess && !submitting && (
            <p role="status" className="text-xs text-green-700 bg-green-50 border border-green-200 rounded px-2 py-1.5">
              {uploadSuccess}
            </p>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={submitting || !form.file}
            className="w-full bg-blue-600 text-white px-3 py-1.5 rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? t('uploading') : t('upload')}
          </button>
        </form>
      </section>

      {/* ── Document List ────────────────────────────────────────────────── */}
      <section className="flex-1 flex flex-col min-h-0">
        <div className="px-4 py-3 border-b">
          <h2 className="text-sm font-semibold">{t('documents')}</h2>
        </div>

        {/* Delete error */}
        {deleteError && (
          <div className="px-4 py-2">
            <p role="alert" className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1.5">
              {deleteError}
            </p>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <p className="px-4 py-3 text-xs text-gray-500">{t('loadingDocuments')}</p>
        )}

        {/* Fetch error */}
        {!loading && fetchError && (
          <p role="alert" className="px-4 py-3 text-xs text-red-600">{fetchError}</p>
        )}

        {/* Empty state */}
        {!loading && !fetchError && documents.length === 0 && (
          <p className="px-4 py-3 text-xs text-gray-500">{t('noDocuments')}</p>
        )}

        {/* Scrollable document list */}
        {!loading && !fetchError && documents.length > 0 && (
          <ul className="flex-1 overflow-y-auto overflow-x-hidden divide-y">
            {documents.map((doc) => {
              const sourceLabel = SOURCES.includes(doc.source as SourceValue)
                ? tAdmin(`sources.${doc.source as SourceValue}`)
                : doc.source;

              return (
                <li key={doc.id} className="px-4 py-3 hover:bg-gray-50 transition-colors">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {doc.title || doc.originalName || '—'}
                      </p>
                      <p className="text-xs text-gray-500 mt-0.5">
                        {sourceLabel} · {formatDate(doc.indexedAt ?? doc.createdAt)}
                      </p>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {/* Download */}
                      <button
                        type="button"
                        onClick={() => void handleDownload(doc.id, doc.originalName || doc.title)}
                        className="text-xs text-blue-600 hover:text-blue-800 font-medium transition-colors"
                        aria-label={`${t('download')} ${doc.title}`}
                      >
                        {t('download')}
                      </button>
                      {/* Delete (admin only) */}
                      {userRole === 'admin' && (
                        <button
                          type="button"
                          onClick={() => void handleDelete(doc.id)}
                          className="text-xs text-red-600 hover:text-red-800 font-medium transition-colors ml-1"
                          aria-label={`Delete ${doc.title}`}
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  </div>
                  {/* Download error for this doc */}
                  {downloadErrors[doc.id] && (
                    <p role="alert" className="text-xs text-red-600 mt-1">{t('errorDownload')}</p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </aside>
  );
}
