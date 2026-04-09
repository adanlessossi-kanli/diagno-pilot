'use client';

/**
 * CitationChip — inline citation reference rendered as [N] in answer text.
 *
 * When clicked, opens CitationPopup with the corresponding DocumentSource.
 * Requirements: 5.5
 */

import { useState } from 'react';
import { CitationPopup } from './CitationPopup';

export interface HighlightInfo {
  bbox: [number, number, number, number];
  page: number;
}

export interface DocumentSource {
  documentId: string;
  title: string;
  source: string;
  section?: string;
  excerpt?: string;
  page?: number;
  highlight?: HighlightInfo;
  confidenceScore?: number;
}

interface CitationChipProps {
  /** 1-based index of the source in the sources list */
  index: number;
  /** The DocumentSource this chip references */
  source: DocumentSource;
}

/**
 * Build a tooltip string from section and page metadata when available.
 */
function buildTooltip(source: DocumentSource): string | undefined {
  const parts: string[] = [];
  if (source.section) parts.push(source.section);
  if (source.page != null) parts.push(`p. ${source.page}`);
  return parts.length > 0 ? parts.join(' — ') : undefined;
}

/**
 * Renders an inline [N] chip. Clicking it opens the CitationPopup.
 * Tooltip shows section and page from LlamaIndex node metadata when available.
 */
export function CitationChip({ index, source }: CitationChipProps) {
  const [open, setOpen] = useState(false);
  const tooltip = buildTooltip(source);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title={tooltip}
        aria-label={`Citation ${index}: ${source.title}${tooltip ? ` (${tooltip})` : ''}`}
        className="inline-flex items-center justify-center mx-0.5 px-1 py-0.5 text-xs font-semibold text-blue-700 bg-blue-100 hover:bg-blue-200 rounded cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400"
      >
        [{index}]
      </button>

      {open && (
        <CitationPopup
          source={source}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
