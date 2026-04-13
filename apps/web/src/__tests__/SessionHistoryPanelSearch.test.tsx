/**
 * Unit tests for SessionHistoryPanel search functionality.
 *
 * Validates:
 * - Req 6.2: Search input filters displayed session entries by preview text
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('../components/ConfirmDialog', () => ({
  ConfirmDialog: ({ open, title, onConfirm, onCancel }: any) => {
    if (!open) return null;
    return (
      <div data-testid="confirm-dialog">
        <p>{title}</p>
        <button onClick={onConfirm}>Confirm</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    );
  },
}));

// ─── Import component under test ─────────────────────────────────────────────

import { SessionHistoryPanel, SessionEntry } from '../components/SessionHistoryPanel';

// ─── Test data ────────────────────────────────────────────────────────────────

const testEntries: SessionEntry[] = [
  { id: '1', preview: 'Malaria treatment options', date: '2024-01-15T10:00:00Z' },
  { id: '2', preview: 'Antibiotic resistance patterns', date: '2024-01-14T09:00:00Z' },
  { id: '3', preview: 'Typhoid fever diagnosis', date: '2024-01-13T08:00:00Z' },
  { id: '4', preview: 'Malaria prevention strategies', date: '2024-01-12T07:00:00Z' },
];

const defaultProps = {
  entries: testEntries,
  activeId: null,
  loading: false,
  error: null,
  hasMore: false,
  loadingMore: false,
  onLoadMore: vi.fn(),
  onSelect: vi.fn(),
  onDelete: vi.fn(),
  selectingId: null,
  deleteMode: 'instant' as const,
  panelTitle: 'Session History',
  emptyMessage: 'No sessions yet',
  deleteLabel: 'Delete',
  announceMessage: null,
  operationError: null,
  searchPlaceholder: 'Search sessions...',
};

// ─── Setup / Teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();

  // IntersectionObserver mock for infinite scroll
  vi.stubGlobal('IntersectionObserver', vi.fn(() => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  })));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('SessionHistoryPanel Search', () => {
  it('search input is rendered when entries exist', () => {
    render(<SessionHistoryPanel {...defaultProps} />);

    const searchInput = screen.getByTestId('session-search-input');
    expect(searchInput).toBeDefined();
    expect(searchInput.getAttribute('placeholder')).toBe('Search sessions...');
  });

  it('typing in search input filters displayed entries', () => {
    render(<SessionHistoryPanel {...defaultProps} />);

    // All 4 entries should be visible initially
    const listbox = screen.getByRole('listbox');
    let options = within(listbox).getAllByRole('option');
    expect(options.length).toBe(4);

    // Type "malaria" to filter
    const searchInput = screen.getByTestId('session-search-input');
    fireEvent.change(searchInput, { target: { value: 'malaria' } });

    // Only 2 entries should match ("Malaria treatment options" and "Malaria prevention strategies")
    options = within(listbox).getAllByRole('option');
    expect(options.length).toBe(2);
  });

  it('clearing search shows all entries again', () => {
    render(<SessionHistoryPanel {...defaultProps} />);

    const searchInput = screen.getByTestId('session-search-input');

    // Filter first
    fireEvent.change(searchInput, { target: { value: 'typhoid' } });
    let listbox = screen.getByRole('listbox');
    let options = within(listbox).getAllByRole('option');
    expect(options.length).toBe(1);

    // Clear the search
    fireEvent.change(searchInput, { target: { value: '' } });
    listbox = screen.getByRole('listbox');
    options = within(listbox).getAllByRole('option');
    expect(options.length).toBe(4);
  });

  it('search is case-insensitive', () => {
    render(<SessionHistoryPanel {...defaultProps} />);

    const searchInput = screen.getByTestId('session-search-input');

    // Search with uppercase
    fireEvent.change(searchInput, { target: { value: 'ANTIBIOTIC' } });
    const listbox = screen.getByRole('listbox');
    const options = within(listbox).getAllByRole('option');
    expect(options.length).toBe(1);
  });
});
