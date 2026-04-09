import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/react';
import React from 'react';
import {
  SessionHistoryPanel,
  removeEntry,
  upsertEntry,
  prependEntry,
} from '../SessionHistoryPanel';
import type { SessionEntry, SessionHistoryPanelProps } from '../SessionHistoryPanel';

afterEach(() => {
  cleanup();
});

const makeEntry = (id: string, preview = `Preview ${id}`, date = '2025-01-15T10:00:00Z'): SessionEntry => ({
  id,
  preview,
  date,
});

const defaultProps: SessionHistoryPanelProps = {
  entries: [makeEntry('1'), makeEntry('2'), makeEntry('3')],
  activeId: null,
  loading: false,
  error: null,
  hasMore: false,
  loadingMore: false,
  onLoadMore: vi.fn(),
  onSelect: vi.fn(),
  onDelete: vi.fn(),
  selectingId: null,
  deleteMode: 'confirm',
  panelTitle: 'Chat History',
  emptyMessage: 'No sessions yet.',
  deleteLabel: 'Delete',
  announceMessage: null,
  operationError: null,
};

// Mock IntersectionObserver
beforeEach(() => {
  const mockObserver = vi.fn(() => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  }));
  vi.stubGlobal('IntersectionObserver', mockObserver);

  // Mock matchMedia for responsive behavior
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

describe('SessionHistoryPanel', () => {
  it('renders panel with toggle button in expanded state by default', () => {
    const { getByTestId } = render(<SessionHistoryPanel {...defaultProps} />);
    const toggle = getByTestId('panel-toggle');
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(toggle.getAttribute('aria-label')).toBe('Collapse session history');
  });

  it('renders panel title when expanded', () => {
    const { getByText } = render(<SessionHistoryPanel {...defaultProps} />);
    expect(getByText('Chat History')).toBeDefined();
  });

  it('renders entries with preview and formatted date', () => {
    const { getByText } = render(<SessionHistoryPanel {...defaultProps} />);
    expect(getByText('Preview 1')).toBeDefined();
    expect(getByText('Preview 2')).toBeDefined();
    expect(getByText('Preview 3')).toBeDefined();
  });

  it('renders listbox with option roles', () => {
    const { container } = render(<SessionHistoryPanel {...defaultProps} />);
    const listbox = container.querySelector('[role="listbox"]');
    expect(listbox).not.toBeNull();
    const options = container.querySelectorAll('[role="option"]');
    expect(options.length).toBe(3);
  });

  it('marks active entry with aria-selected=true', () => {
    const { container } = render(
      <SessionHistoryPanel {...defaultProps} activeId="2" />,
    );
    const options = container.querySelectorAll('[role="option"]');
    expect(options[0]?.getAttribute('aria-selected')).toBe('false');
    expect(options[1]?.getAttribute('aria-selected')).toBe('true');
    expect(options[2]?.getAttribute('aria-selected')).toBe('false');
  });

  it('marks no entry as active when activeId is null', () => {
    const { container } = render(<SessionHistoryPanel {...defaultProps} />);
    const selected = container.querySelectorAll('[aria-selected="true"]');
    expect(selected.length).toBe(0);
  });

  it('shows loading state', () => {
    const { container } = render(
      <SessionHistoryPanel {...defaultProps} loading={true} entries={[]} />,
    );
    const busy = container.querySelector('[aria-busy="true"]');
    expect(busy).not.toBeNull();
  });

  it('shows error state', () => {
    const { getByText } = render(
      <SessionHistoryPanel {...defaultProps} error="Error loading sessions." entries={[]} />,
    );
    expect(getByText('Error loading sessions.')).toBeDefined();
  });

  it('shows empty state', () => {
    const { getByText } = render(
      <SessionHistoryPanel {...defaultProps} entries={[]} />,
    );
    expect(getByText('No sessions yet.')).toBeDefined();
  });

  it('calls onSelect when entry is clicked', () => {
    const onSelect = vi.fn();
    const { getByTestId } = render(
      <SessionHistoryPanel {...defaultProps} onSelect={onSelect} />,
    );
    fireEvent.click(getByTestId('session-entry-2'));
    expect(onSelect).toHaveBeenCalledWith('2');
  });

  it('does not call onSelect when selectingId is set', () => {
    const onSelect = vi.fn();
    const { getByTestId } = render(
      <SessionHistoryPanel {...defaultProps} onSelect={onSelect} selectingId="1" />,
    );
    fireEvent.click(getByTestId('session-entry-2'));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('shows spinner on selecting entry', () => {
    const { getByTestId } = render(
      <SessionHistoryPanel {...defaultProps} selectingId="2" />,
    );
    const entry = getByTestId('session-entry-2');
    const spinner = entry.querySelector('.animate-spin');
    expect(spinner).not.toBeNull();
  });

  it('toggles collapse state on toggle button click', () => {
    const { getByTestId } = render(<SessionHistoryPanel {...defaultProps} />);
    const toggle = getByTestId('panel-toggle');
    expect(toggle.getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
  });

  it('shows confirm dialog when delete button clicked in confirm mode', () => {
    const { getByTestId, container } = render(
      <SessionHistoryPanel {...defaultProps} deleteMode="confirm" />,
    );
    fireEvent.click(getByTestId('delete-btn-1'));
    const dialog = container.querySelector('[role="alertdialog"]');
    expect(dialog).not.toBeNull();
  });

  it('calls onDelete immediately in instant mode', () => {
    const onDelete = vi.fn();
    const { getByTestId } = render(
      <SessionHistoryPanel {...defaultProps} deleteMode="instant" onDelete={onDelete} />,
    );
    fireEvent.click(getByTestId('delete-btn-1'));
    expect(onDelete).toHaveBeenCalledWith('1');
  });

  it('displays operationError as inline message', () => {
    const { getByText } = render(
      <SessionHistoryPanel {...defaultProps} operationError="Something went wrong" />,
    );
    expect(getByText('Something went wrong')).toBeDefined();
  });

  it('renders aria-live region with announceMessage', () => {
    const { getByTestId } = render(
      <SessionHistoryPanel {...defaultProps} announceMessage="Session loaded." />,
    );
    expect(getByTestId('announce-region').textContent).toBe('Session loaded.');
  });

  it('renders loadingMore indicator', () => {
    const { getByText } = render(
      <SessionHistoryPanel {...defaultProps} loadingMore={true} hasMore={true} />,
    );
    expect(getByText('Loading more...')).toBeDefined();
  });

  it('supports keyboard ArrowDown navigation', () => {
    const { container } = render(<SessionHistoryPanel {...defaultProps} />);
    const listbox = container.querySelector('[role="listbox"]')!;
    const options = container.querySelectorAll('[role="option"]');

    // Initially first entry has tabindex=0
    expect(options[0]?.getAttribute('tabindex')).toBe('0');
    expect(options[1]?.getAttribute('tabindex')).toBe('-1');

    fireEvent.keyDown(listbox, { key: 'ArrowDown' });
    // After re-render, check the second option
    const updatedOptions = container.querySelectorAll('[role="option"]');
    expect(updatedOptions[1]?.getAttribute('tabindex')).toBe('0');
  });

  it('supports keyboard ArrowUp navigation', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <SessionHistoryPanel {...defaultProps} onSelect={onSelect} />,
    );
    const listbox = container.querySelector('[role="listbox"]')!;

    // Move down first
    fireEvent.keyDown(listbox, { key: 'ArrowDown' });
    fireEvent.keyDown(listbox, { key: 'ArrowDown' });

    // Now at index 2, move up
    fireEvent.keyDown(listbox, { key: 'ArrowUp' });
    const options = container.querySelectorAll('[role="option"]');
    expect(options[1]?.getAttribute('tabindex')).toBe('0');
  });

  it('supports Enter key to select', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <SessionHistoryPanel {...defaultProps} onSelect={onSelect} />,
    );
    const listbox = container.querySelector('[role="listbox"]')!;
    fireEvent.keyDown(listbox, { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith('1');
  });

  it('supports Delete key to trigger delete', () => {
    const onDelete = vi.fn();
    const { container } = render(
      <SessionHistoryPanel {...defaultProps} deleteMode="instant" onDelete={onDelete} />,
    );
    const listbox = container.querySelector('[role="listbox"]')!;
    fireEvent.keyDown(listbox, { key: 'Delete' });
    expect(onDelete).toHaveBeenCalledWith('1');
  });

  it('preserves entry order as given', () => {
    const entries = [makeEntry('c'), makeEntry('a'), makeEntry('b')];
    const { container } = render(
      <SessionHistoryPanel {...defaultProps} entries={entries} />,
    );
    const options = container.querySelectorAll('[role="option"]');
    expect(options[0]?.textContent).toContain('Preview c');
    expect(options[1]?.textContent).toContain('Preview a');
    expect(options[2]?.textContent).toContain('Preview b');
  });
});

describe('removeEntry', () => {
  it('removes the entry with the given id', () => {
    const entries = [makeEntry('1'), makeEntry('2'), makeEntry('3')];
    const result = removeEntry(entries, '2');
    expect(result).toEqual([makeEntry('1'), makeEntry('3')]);
  });

  it('returns same array content when id not found', () => {
    const entries = [makeEntry('1'), makeEntry('2')];
    const result = removeEntry(entries, '99');
    expect(result).toEqual(entries);
  });

  it('returns empty array when removing from single-element array', () => {
    const result = removeEntry([makeEntry('1')], '1');
    expect(result).toEqual([]);
  });
});

describe('upsertEntry', () => {
  it('prepends new entry when id does not exist', () => {
    const entries = [makeEntry('1'), makeEntry('2')];
    const newEntry = makeEntry('3', 'New');
    const result = upsertEntry(entries, newEntry);
    expect(result.length).toBe(3);
    expect(result[0]).toEqual(newEntry);
  });

  it('moves existing entry to top with updated data', () => {
    const entries = [makeEntry('1'), makeEntry('2'), makeEntry('3')];
    const updated = makeEntry('2', 'Updated');
    const result = upsertEntry(entries, updated);
    expect(result.length).toBe(3);
    expect(result[0]).toEqual(updated);
    expect(result.find((e) => e.id === '2')).toEqual(updated);
  });

  it('preserves order of other entries', () => {
    const entries = [makeEntry('1'), makeEntry('2'), makeEntry('3')];
    const updated = makeEntry('2', 'Updated');
    const result = upsertEntry(entries, updated);
    expect(result[1].id).toBe('1');
    expect(result[2].id).toBe('3');
  });
});

describe('prependEntry', () => {
  it('adds entry at index 0', () => {
    const entries = [makeEntry('1'), makeEntry('2')];
    const newEntry = makeEntry('3', 'New');
    const result = prependEntry(entries, newEntry);
    expect(result.length).toBe(3);
    expect(result[0]).toEqual(newEntry);
  });

  it('preserves existing entries in order', () => {
    const entries = [makeEntry('1'), makeEntry('2')];
    const newEntry = makeEntry('3', 'New');
    const result = prependEntry(entries, newEntry);
    expect(result[1]).toEqual(entries[0]);
    expect(result[2]).toEqual(entries[1]);
  });

  it('works with empty array', () => {
    const newEntry = makeEntry('1');
    const result = prependEntry([], newEntry);
    expect(result).toEqual([newEntry]);
  });
});
