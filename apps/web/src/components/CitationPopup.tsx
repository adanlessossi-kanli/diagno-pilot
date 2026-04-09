'use client';

/**
 * CitationPopup — modal/drawer that shows the source PDF page with a yellow
 * highlight overlay at the cited passage position.
 *
 * - Fetches the presigned S3 URL via GET /api/v1/documents/{id}/view
 * - Renders the PDF page via react-pdf
 * - Overlays a yellow rectangle at highlight.bbox coordinates
 * - Displays only the excerpt text if highlight is absent (REQ 5.7, 5.8)
 * - Closes via Escape or click outside (REQ 5.9)
 *
 * Requirements: 5.6, 5.7, 5.9
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { DocumentSource } from './CitationChip';

// Lazy-load react-pdf to avoid SSR issues
let Document: React.ComponentType<any> | null = null;
let Page: React.ComponentType<any> | null = null;

interface CitationPopupProps {
  source: DocumentSource;
  onClose: () => void;
}

interface PresignedUrlResponse {
  url: string;
  expires_in: number;
}

/**
 * Fetch the presigned S3 URL for a document.
 */
async function fetchPresignedUrl(documentId: string): Promise<string> {
  const res = await fetch(`/api/v1/documents/${encodeURIComponent(documentId)}/view`, {
    credentials: 'include',
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch document URL: ${res.status}`);
  }
  const data: PresignedUrlResponse = await res.json();
  return data.url;
}

export function CitationPopup({ source, onClose }: CitationPopupProps) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pageWidth, setPageWidth] = useState(600);
  const [pdfComponents, setPdfComponents] = useState<{ Document: any; Page: any } | null>(null);

  const hasHighlight = Boolean(source.highlight);
  const targetPage = source.highlight ? source.highlight.page + 1 : (source.page ?? 1); // react-pdf uses 1-based pages

  // Load react-pdf lazily (client-side only)
  useEffect(() => {
    if (!hasHighlight) return;
    import('react-pdf').then((mod) => {
      // Configure worker
      const { pdfjs } = mod;
      if (pdfjs && !pdfjs.GlobalWorkerOptions.workerSrc) {
        pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;
      }
      setPdfComponents({ Document: mod.Document, Page: mod.Page });
    }).catch(() => {
      setPdfError('PDF viewer could not be loaded.');
    });
  }, [hasHighlight]);

  // Fetch presigned URL when popup opens (only if we have a highlight to show)
  useEffect(() => {
    if (!hasHighlight) return;
    setPdfLoading(true);
    fetchPresignedUrl(source.documentId)
      .then((url) => {
        setPdfUrl(url);
        setPdfLoading(false);
      })
      .catch((err) => {
        setPdfError(err.message ?? 'Failed to load document.');
        setPdfLoading(false);
      });
  }, [source.documentId, hasHighlight]);

  // Close on Escape key (REQ 5.9)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Close on click outside (REQ 5.9)
  const handleOverlayClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === overlayRef.current) onClose();
    },
    [onClose],
  );

  return (
    <div
      ref={overlayRef}
      role="dialog"
      aria-modal="true"
      aria-label={`Citation: ${source.title}`}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
    >
      <div className="relative bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-start justify-between p-4 border-b">
          <div className="flex-1 min-w-0 pr-4">
            <h2 className="text-base font-semibold text-gray-900 truncate">{source.title}</h2>
            {source.source && (
              <p className="text-xs text-gray-500 mt-0.5">{source.source}</p>
            )}
            {source.section && (
              <p className="text-xs text-gray-400 mt-0.5 italic">{source.section}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fermer"
            className="flex-shrink-0 p-1 rounded hover:bg-gray-100 text-gray-500 hover:text-gray-700 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="p-4">
          {/* Case 1: No highlight — show excerpt only (REQ 5.7) */}
          {!hasHighlight && (
            <div>
              {source.excerpt ? (
                <blockquote className="border-l-4 border-blue-300 pl-4 text-sm text-gray-700 italic">
                  {source.excerpt}
                </blockquote>
              ) : (
                <p className="text-sm text-gray-500">Aucun extrait disponible.</p>
              )}
            </div>
          )}

          {/* Case 2: Has highlight — render PDF with overlay (REQ 5.6) */}
          {hasHighlight && (
            <div>
              {pdfLoading && (
                <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
                  Chargement du document…
                </div>
              )}

              {pdfError && (
                <div className="py-4">
                  <p className="text-sm text-red-600 mb-3">{pdfError}</p>
                  {source.excerpt && (
                    <blockquote className="border-l-4 border-blue-300 pl-4 text-sm text-gray-700 italic">
                      {source.excerpt}
                    </blockquote>
                  )}
                </div>
              )}

              {pdfUrl && pdfComponents && !pdfError && (
                <PdfPageWithHighlight
                  url={pdfUrl}
                  pageNumber={targetPage}
                  bbox={source.highlight!.bbox}
                  pageWidth={pageWidth}
                  Document={pdfComponents.Document}
                  Page={pdfComponents.Page}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal: PDF page renderer with highlight overlay
// ---------------------------------------------------------------------------

interface PdfPageWithHighlightProps {
  url: string;
  pageNumber: number;
  bbox: [number, number, number, number];
  pageWidth: number;
  Document: React.ComponentType<any>;
  Page: React.ComponentType<any>;
}

function PdfPageWithHighlight({
  url,
  pageNumber,
  bbox,
  pageWidth,
  Document,
  Page,
}: PdfPageWithHighlightProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pdfPageHeight, setPdfPageHeight] = useState<number | null>(null);
  const [pdfPageWidth, setPdfPageWidth] = useState<number | null>(null);
  const [renderWidth, setRenderWidth] = useState(pageWidth);

  // Measure container width via callback ref (avoids setState in useEffect)
  const measureRef = useCallback(
    (node: HTMLDivElement | null) => {
      (containerRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
      if (node) {
        setRenderWidth(node.clientWidth || pageWidth);
      }
    },
    [pageWidth],
  );

  // Compute highlight rectangle in rendered pixel coordinates
  // bbox is [x0, y0, x1, y1] in PDF user-space (points, origin bottom-left)
  const highlightStyle = (() => {
    if (!pdfPageWidth || !pdfPageHeight) return null;
    const scaleX = renderWidth / pdfPageWidth;
    const scaleY = (pdfPageHeight * scaleX) / pdfPageHeight; // same scale
    const scale = scaleX;

    const [x0, y0Pdf, x1, y1Pdf] = bbox;
    // PDF y-axis is bottom-up; canvas y-axis is top-down
    const left = x0 * scale;
    const top = (pdfPageHeight - y1Pdf) * scale;
    const width = (x1 - x0) * scale;
    const height = (y1Pdf - y0Pdf) * scale;

    return {
      position: 'absolute' as const,
      left: `${left}px`,
      top: `${top}px`,
      width: `${Math.max(width, 4)}px`,
      height: `${Math.max(height, 4)}px`,
      backgroundColor: 'rgba(255, 220, 0, 0.45)',
      border: '1.5px solid rgba(200, 160, 0, 0.7)',
      borderRadius: '2px',
      pointerEvents: 'none' as const,
    };
  })();

  return (
    <div ref={measureRef} className="relative w-full overflow-hidden rounded border border-gray-200">
      <Document
        file={url}
        loading={
          <div className="flex items-center justify-center py-8 text-gray-400 text-sm">
            Chargement du PDF…
          </div>
        }
        error={
          <div className="py-4 text-sm text-red-500">
            Impossible de charger le PDF.
          </div>
        }
      >
        <div className="relative">
          <Page
            pageNumber={pageNumber}
            width={renderWidth}
            onLoadSuccess={(page: { originalWidth: number; originalHeight: number }) => {
              setPdfPageWidth(page.originalWidth);
              setPdfPageHeight(page.originalHeight);
            }}
            renderTextLayer={false}
            renderAnnotationLayer={false}
          />
          {/* Yellow highlight overlay */}
          {highlightStyle && (
            <div
              style={highlightStyle}
              aria-hidden="true"
              data-testid="citation-highlight"
            />
          )}
        </div>
      </Document>
    </div>
  );
}
