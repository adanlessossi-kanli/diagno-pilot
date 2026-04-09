'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import Link from 'next/link';
import { createApiClient } from '@diagno-pilot/api-client';
import type { PaginatedResponse } from '@diagno-pilot/api-client';
import type { Consultation } from '@diagno-pilot/types';
import { useAuth } from '../../../../contexts/AuthContext';

const PAGE_SIZE = 20;

export default function DiagnoseHistoryPage() {
  const t = useTranslations('diagnose');
  const { user } = useAuth();
  const locale = useLocale();

  const apiClient = useMemo(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
    return createApiClient(baseUrl, undefined, () => locale);
  }, [locale]);

  const [page, setPage] = useState(1);
  const [data, setData] = useState<PaginatedResponse<Consultation> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const lastFetchedPage = useRef<number | null>(null);

  useEffect(() => {
    if (!user) return;
    if (lastFetchedPage.current === page) return;
    let cancelled = false;
    lastFetchedPage.current = page;

    (async () => {
      setLoading(true);
      setError('');
      try {
        const result = await apiClient.diagnose.listMyConsultations(page, PAGE_SIZE);
        if (!cancelled) setData(result);
      } catch {
        if (!cancelled) setError('history.errorFetch');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [user, page, apiClient]);

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  const handlePrevious = () => {
    lastFetchedPage.current = null;
    setPage((p) => Math.max(1, p - 1));
  };

  const handleNext = () => {
    lastFetchedPage.current = null;
    setPage((p) => p + 1);
  };

  return (
    <main className="min-h-screen p-8 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">{t('history.title')}</h1>

      {loading && <p className="text-sm text-gray-500">{t('history.loading')}</p>}
      {error && (
        <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
          {t(error)}
        </p>
      )}

      {!loading && !error && data && data.items.length === 0 && (
        <p className="text-sm text-gray-500">{t('history.noHistory')}</p>
      )}

      {!loading && !error && data && data.items.length > 0 && (
        <>
          <ul className="space-y-3" data-testid="history-list">
            {data.items.map((consultation) => {
              const symptomSummary = consultation.symptoms
                .slice(0, 3)
                .map((s) => s.name)
                .join(', ');
              const topDiag = consultation.diagnoses[0];
              return (
                <li
                  key={consultation.id}
                  className="border rounded-lg p-4 space-y-2 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-500">
                      {new Date(consultation.createdAt ?? '').toLocaleDateString()}
                    </span>
                    <Link
                      href={`/${locale}/diagnose/history/${consultation.id}`}
                      className="text-blue-600 hover:underline text-xs font-medium"
                    >
                      {t('history.viewDetails')}
                    </Link>
                  </div>
                  <p className="text-sm text-gray-700">
                    <span className="font-medium">{t('history.symptoms')}:</span> {symptomSummary || '—'}
                  </p>
                  {topDiag && (
                    <p className="text-sm">
                      <span className="font-medium">{t('history.topDiagnosis')}:</span>{' '}
                      {topDiag.condition} ({Math.round(topDiag.probability * 100)}%)
                    </p>
                  )}
                </li>
              );
            })}
          </ul>

          {/* Pagination */}
          <div className="flex items-center justify-between mt-6">
            <button
              type="button"
              disabled={page <= 1}
              onClick={handlePrevious}
              className="px-3 py-1.5 text-sm border rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
              data-testid="prev-button"
            >
              {t('history.previous')}
            </button>
            <span className="text-sm text-gray-500">
              {page} / {totalPages || 1}
            </span>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={handleNext}
              className="px-3 py-1.5 text-sm border rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
              data-testid="next-button"
            >
              {t('history.next')}
            </button>
          </div>
        </>
      )}

      <div className="mt-6">
        <Link
          href={`/${locale}/diagnose`}
          className="text-blue-600 hover:underline text-sm"
        >
          ← {t('title')}
        </Link>
      </div>
    </main>
  );
}
