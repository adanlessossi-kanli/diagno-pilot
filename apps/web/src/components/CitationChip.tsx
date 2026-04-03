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
  document_id: string;
  title: string;
  source: string;
  section?: string;
  excerpt?: string;
  page?: number;
  highlight?: HighlightInfo;
  confidence_score?: number;
}

interface CitationChipProps {
  /** 1-based index of the source in the sources list */
  index: number;
  /** The DocumentSource this chip references */
  source: DocumentSource;
}

/**
 * Renders an inline [N] chip. Clicking it opens the CitationPopup.
 */
export function CitationChip({ index, source }: CitationChipProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`Citation ${index}: ${source.title}`}
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
