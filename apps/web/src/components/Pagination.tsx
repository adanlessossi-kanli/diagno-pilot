'use client';

// Composant Pagination réutilisable — REQ 8.4, 8.5
// Synchronise l'état page avec le query param URL (?page=N)

import { useCallback } from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';

interface PaginationProps {
  /** Page courante (1-indexée) */
  page: number;
  /** Taille de page */
  pageSize: number;
  /** Nombre total d'éléments */
  total: number;
}

export default function Pagination({ page, pageSize, total }: PaginationProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // Plage courante, ex. « 21–40 sur 150 »
  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, total);

  const goToPage = useCallback(
    (p: number) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set('page', String(p));
      router.push(`${pathname}?${params.toString()}`);
    },
    [router, pathname, searchParams],
  );

  if (total === 0) return null;

  // Calcul des numéros de page à afficher (fenêtre glissante de 5)
  const pageNumbers: number[] = [];
  const windowSize = 5;
  let start = Math.max(1, page - Math.floor(windowSize / 2));
  const end = Math.min(totalPages, start + windowSize - 1);
  start = Math.max(1, end - windowSize + 1);
  for (let i = start; i <= end; i++) {
    pageNumbers.push(i);
  }

  return (
    <nav
      aria-label="Pagination"
      className="flex flex-col items-center gap-3 mt-6"
    >
      {/* Plage courante */}
      <p className="text-sm text-gray-500">
        {rangeStart}–{rangeEnd} sur {total}
      </p>

      {/* Contrôles */}
      <div className="flex items-center gap-1">
        {/* Précédent */}
        <button
          type="button"
          onClick={() => goToPage(page - 1)}
          disabled={page <= 1}
          aria-label="Page précédente"
          className="px-3 py-1.5 text-sm border rounded-md hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          ‹
        </button>

        {/* Numéros de page */}
        {pageNumbers.map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => goToPage(n)}
            aria-current={n === page ? 'page' : undefined}
            className={`px-3 py-1.5 text-sm border rounded-md transition-colors ${
              n === page
                ? 'bg-primary-600 text-white border-primary-600 font-semibold'
                : 'hover:bg-gray-50'
            }`}
          >
            {n}
          </button>
        ))}

        {/* Suivant */}
        <button
          type="button"
          onClick={() => goToPage(page + 1)}
          disabled={page >= totalPages}
          aria-label="Page suivante"
          className="px-3 py-1.5 text-sm border rounded-md hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          ›
        </button>
      </div>
    </nav>
  );
}
