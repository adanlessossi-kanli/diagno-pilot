'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { ConfirmDialog } from './ConfirmDialog';

// ── Interfaces ──────────────────────────────────────────────────────────────

export interface SessionEntry {
  id: string;
  preview: string;
  date: string; // ISO date string
}

export interface SessionHistoryPanelProps {
  entries: SessionEntry[];
  activeId: string | null;
  loading: boolean;
  error: string | null;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  selectingId: string | null;
  deleteMode: 'confirm' | 'instant';
  panelTitle: string;
  emptyMessage: string;
  deleteLabel: string;
  announceMessage: string | null;
  operationError: string | null;
}

// ── Pure helper functions (tested by PBT 4.9, 4.10, 4.11) ──────────────────

export function removeEntry(entries: SessionEntry[], id: string): SessionEntry[] {
  return entries.filter((e) => e.id !== id);
}

export function upsertEntry(entries: SessionEntry[], entry: SessionEntry): SessionEntry[] {
  const filtered = entries.filter((e) => e.id !== entry.id);
  return [entry, ...filtered];
}

export function prependEntry(entries: SessionEntry[], entry: SessionEntry): SessionEntry[] {
  return [entry, ...entries];
}

// ── Helper: format ISO date for display ─────────────────────────────────────

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

// ── SVG Icons ───────────────────────────────────────────────────────────────

function ChevronLeftIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

function ChevronRightIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="9 6 15 12 9 18" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <line x1="1" y1="1" x2="23" y2="23" />
      <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
    </svg>
  );
}

function SpinnerIcon() {
  return (
    <svg className="animate-spin h-4 w-4 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

// ── Main Component ──────────────────────────────────────────────────────────

export function SessionHistoryPanel({
  entries,
  activeId,
  loading,
  error,
  hasMore,
  loadingMore,
  onLoadMore,
  onSelect,
  onDelete,
  selectingId,
  deleteMode,
  panelTitle,
  emptyMessage,
  deleteLabel,
  announceMessage,
  operationError,
}: SessionHistoryPanelProps) {
  const [expanded, setExpanded] = useState(true);
  const [isNarrow, setIsNarrow] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(0);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const listRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const entryRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const prevEntriesLenRef = useRef(entries.length);

  // ── Responsive: auto-collapse on narrow viewports ──
  useEffect(() => {
    const mql = window.matchMedia('(max-width: 767px)');
    const handler = (e: MediaQueryListEvent | MediaQueryList) => {
      setIsNarrow(e.matches);
      if (e.matches) setExpanded(false);
    };
    handler(mql);
    mql.addEventListener('change', handler as (e: MediaQueryListEvent) => void);
    return () => mql.removeEventListener('change', handler as (e: MediaQueryListEvent) => void);
  }, []);

  // ── IntersectionObserver for infinite scroll ──
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (observerEntries) => {
        if (observerEntries[0]?.isIntersecting && hasMore && !loadingMore) {
          onLoadMore();
        }
      },
      { root: listRef.current, threshold: 0.1 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, onLoadMore]);

  // ── Focus management after deletion ──
  useEffect(() => {
    const prevLen = prevEntriesLenRef.current;
    const currLen = entries.length;
    if (currLen < prevLen && currLen > 0) {
      // An entry was removed — move focus
      const newIndex = Math.min(focusedIndex, currLen - 1);
      requestAnimationFrame(() => {
        setFocusedIndex(newIndex);
        entryRefs.current.get(newIndex)?.focus();
      });
    }
    prevEntriesLenRef.current = currLen;
  }, [entries.length, focusedIndex]);

  // ── Delete action (confirm vs instant) ──
  const handleDeleteAction = useCallback(
    (id: string) => {
      if (deleteMode === 'confirm') {
        setConfirmDeleteId(id);
      } else {
        onDelete(id);
      }
    },
    [deleteMode, onDelete],
  );

  // ── Keyboard navigation ──
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (entries.length === 0) return;

      switch (e.key) {
        case 'ArrowDown': {
          e.preventDefault();
          const next = Math.min(focusedIndex + 1, entries.length - 1);
          setFocusedIndex(next);
          entryRefs.current.get(next)?.focus();
          break;
        }
        case 'ArrowUp': {
          e.preventDefault();
          const prev = Math.max(focusedIndex - 1, 0);
          setFocusedIndex(prev);
          entryRefs.current.get(prev)?.focus();
          break;
        }
        case 'Enter': {
          e.preventDefault();
          const entry = entries[focusedIndex];
          if (entry && !selectingId) {
            onSelect(entry.id);
          }
          break;
        }
        case 'Delete': {
          e.preventDefault();
          const entry = entries[focusedIndex];
          if (entry) {
            handleDeleteAction(entry.id);
          }
          break;
        }
      }
    },
    [entries, focusedIndex, selectingId, onSelect, handleDeleteAction],
  );

  const handleConfirmDelete = useCallback(() => {
    if (confirmDeleteId) {
      onDelete(confirmDeleteId);
      setConfirmDeleteId(null);
    }
  }, [confirmDeleteId, onDelete]);

  const handleCancelDelete = useCallback(() => {
    setConfirmDeleteId(null);
  }, []);

  // ── Toggle ──
  const toggleExpanded = useCallback(() => {
    setExpanded((prev) => !prev);
  }, []);

  // ── Backdrop click (narrow overlay) ──
  const handleBackdropClick = useCallback(() => {
    setExpanded(false);
  }, []);

  // ── Clamp focusedIndex when entries change ──
  useEffect(() => {
    if (entries.length > 0 && focusedIndex >= entries.length) {
      requestAnimationFrame(() => {
        setFocusedIndex(entries.length - 1);
      });
    }
  }, [entries.length, focusedIndex]);

  // ── Render ──

  const isExpanded = expanded;
  const isOverlay = isNarrow && isExpanded;

  return (
    <>
      {/* Backdrop for narrow overlay */}
      {isOverlay && (
        <div
          className="fixed inset-0 z-40 bg-black/40"
          aria-hidden="true"
          onClick={handleBackdropClick}
        />
      )}

      <div
        className={`
          ${isNarrow && isExpanded ? 'fixed top-0 left-0 z-50 h-full' : 'relative'}
          ${isExpanded ? 'w-72' : 'w-12'}
          flex flex-col border-r border-gray-200 bg-white transition-all duration-200
          ${isNarrow && !isExpanded ? '' : ''}
          shrink-0
        `}
        data-testid="session-history-panel"
      >
        {/* Toggle button */}
        <button
          type="button"
          onClick={toggleExpanded}
          aria-expanded={isExpanded}
          aria-label={isExpanded ? 'Collapse session history' : 'Expand session history'}
          className="flex items-center justify-center h-10 w-full border-b border-gray-200 hover:bg-gray-50 transition-colors duration-150"
          data-testid="panel-toggle"
        >
          {isExpanded ? <ChevronLeftIcon /> : <ChevronRightIcon />}
        </button>

        {isExpanded && (
          <div className="flex flex-col flex-1 overflow-hidden">
            {/* Panel title */}
            <h2 className="px-3 py-2 text-sm font-semibold text-gray-700 border-b border-gray-100">
              {panelTitle}
            </h2>

            {/* Operation error */}
            {operationError && (
              <div className="px-3 py-2 text-xs text-red-600 bg-red-50 border-b border-red-100" role="alert">
                {operationError}
              </div>
            )}

            {/* Loading state */}
            {loading && (
              <div className="flex items-center justify-center py-8" aria-busy="true">
                <SpinnerIcon />
                <span className="ml-2 text-sm text-gray-500">Loading...</span>
              </div>
            )}

            {/* Error state */}
            {!loading && error && (
              <div className="px-3 py-4 text-sm text-red-600" role="alert">
                {error}
              </div>
            )}

            {/* Empty state */}
            {!loading && !error && entries.length === 0 && (
              <div className="px-3 py-8 text-sm text-gray-500 text-center">
                {emptyMessage}
              </div>
            )}

            {/* Entry list */}
            {!loading && !error && entries.length > 0 && (
              <div
                ref={listRef}
                role="listbox"
                aria-label={panelTitle}
                className="flex-1 overflow-y-auto"
                onKeyDown={handleKeyDown}
              >
                {entries.map((entry, index) => {
                  const isActive = entry.id === activeId;
                  const isFocused = index === focusedIndex;
                  const isSelecting = entry.id === selectingId;

                  return (
                    <div
                      key={entry.id}
                      ref={(el) => {
                        if (el) entryRefs.current.set(index, el);
                        else entryRefs.current.delete(index);
                      }}
                      role="option"
                      aria-selected={isActive}
                      tabIndex={isFocused ? 0 : -1}
                      onClick={() => {
                        if (!selectingId) {
                          setFocusedIndex(index);
                          onSelect(entry.id);
                        }
                      }}
                      className={`
                        group relative px-3 py-2 cursor-pointer border-b border-gray-100
                        transition-colors duration-100
                        ${isActive ? 'bg-blue-50 border-l-2 border-l-blue-500' : 'hover:bg-gray-50'}
                        ${isFocused ? 'ring-2 ring-inset ring-blue-300' : ''}
                      `}
                      data-testid={`session-entry-${entry.id}`}
                    >
                      <div className="flex items-start justify-between gap-1">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-gray-800 truncate">{entry.preview}</p>
                          <p className="text-xs text-gray-400 mt-0.5">{formatDate(entry.date)}</p>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          {isSelecting && <SpinnerIcon />}
                          <button
                            type="button"
                            aria-label={`${deleteLabel} ${entry.preview}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteAction(entry.id);
                            }}
                            className="opacity-0 group-hover:opacity-100 focus:opacity-100 p-1 rounded hover:bg-gray-200 text-gray-500 hover:text-red-600 transition-all duration-150"
                            data-testid={`delete-btn-${entry.id}`}
                          >
                            {deleteMode === 'confirm' ? <TrashIcon /> : <EyeOffIcon />}
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}

                {/* Sentinel for infinite scroll */}
                <div ref={sentinelRef} className="h-1" aria-hidden="true" />

                {/* Loading more indicator */}
                {loadingMore && (
                  <div className="flex items-center justify-center py-3">
                    <SpinnerIcon />
                    <span className="ml-2 text-xs text-gray-400">Loading more...</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* aria-live region for announcements */}
      <div aria-live="polite" className="sr-only" data-testid="announce-region">
        {announceMessage}
      </div>

      {/* Confirm dialog for delete mode */}
      <ConfirmDialog
        open={confirmDeleteId !== null}
        title="Delete session?"
        message="This action cannot be undone."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={handleConfirmDelete}
        onCancel={handleCancelDelete}
      />
    </>
  );
}
