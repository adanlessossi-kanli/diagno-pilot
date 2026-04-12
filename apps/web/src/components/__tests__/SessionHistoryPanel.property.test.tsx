import fc from 'fast-check';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, fireEvent, act } from '@testing-library/react';
import React from 'react';
import {
  SessionHistoryPanel,
  removeEntry,
  upsertEntry,
  prependEntry,
} from '../SessionHistoryPanel';
import type { SessionEntry, SessionHistoryPanelProps } from '../SessionHistoryPanel';

// ─── Setup ────────────────────────────────────────────────────────────────────

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  const mockObserver = vi.fn(() => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  }));
  vi.stubGlobal('IntersectionObserver', mockObserver);

  // Mock requestAnimationFrame to fire synchronously (jsdom doesn't run rAF callbacks reliably)
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    cb(0);
    return 0;
  });

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

// ─── Shared helpers ───────────────────────────────────────────────────────────

const defaultProps: SessionHistoryPanelProps = {
  entries: [],
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

// ─── Generators ───────────────────────────────────────────────────────────────

/** Generate a valid ISO date string between 2000 and 2030. */
const isoDateArb = fc
  .date({ min: new Date('2000-01-01T00:00:00Z'), max: new Date('2030-12-31T23:59:59Z'), noInvalidDate: true })
  .map((d) => d.toISOString());

/** Generate a non-empty alphanumeric preview string. */
const previewArb = fc.stringMatching(/^[a-zA-Z0-9 ]+$/, { maxLength: 60 }).filter((s) => s.length >= 1);

/** Generate a SessionEntry with a unique id, non-empty preview, and valid ISO date. */
const sessionEntryArb = fc.record({
  id: fc.uuid(),
  preview: previewArb,
  date: isoDateArb,
});

/** Generate an array of SessionEntry objects with unique IDs. */
const sessionEntriesArb = (opts?: { minLength?: number; maxLength?: number }) =>
  fc
    .array(sessionEntryArb, {
      minLength: opts?.minLength ?? 1,
      maxLength: opts?.maxLength ?? 30,
    })
    .map((entries) => {
      // Deduplicate by id
      const seen = new Set<string>();
      return entries.filter((e) => {
        if (seen.has(e.id)) return false;
        seen.add(e.id);
        return true;
      });
    })
    .filter((entries) => entries.length >= (opts?.minLength ?? 1));

// ─── Property 1 ───────────────────────────────────────────────────────────────

describe('Feature: session-history-panels, Property 1: Entry display contains preview and formatted date', () => {
  /**
   * **Validates: Requirements 1.2, 4.2**
   *
   * For any array of SessionEntry objects with non-empty preview and valid ISO
   * date strings, rendering the SessionHistoryPanel SHALL produce a list where
   * each rendered entry contains the entry's preview text and a formatted
   * representation of its date (at minimum the year).
   */
  it('each rendered entry contains its preview text and the year from its date', () => {
    fc.assert(
      fc.property(sessionEntriesArb({ minLength: 1, maxLength: 20 }), (entries) => {
        cleanup();
        const { container } = render(
          <SessionHistoryPanel {...defaultProps} entries={entries} />,
        );

        const options = container.querySelectorAll('[role="option"]');
        expect(options.length).toBe(entries.length);

        for (let i = 0; i < entries.length; i++) {
          const entry = entries[i]!;
          const optionText = options[i]!.textContent ?? '';

          // Preview text must appear in the rendered entry
          expect(optionText).toContain(entry.preview);

          // The year from the date must appear (locale-independent check)
          const year = new Date(entry.date).getFullYear().toString();
          expect(optionText).toContain(year);
        }

        cleanup();
      }),
      { numRuns: 100 },
    );
  });
});

// ─── Property 2 ───────────────────────────────────────────────────────────────

describe('Feature: session-history-panels, Property 2: Panel preserves input entry order', () => {
  /**
   * **Validates: Requirements 1.3, 4.3**
   *
   * For any array of SessionEntry objects passed as entries to
   * SessionHistoryPanel, the rendered list SHALL display entries in the same
   * order as the input array. The panel does not sort — ordering responsibility
   * belongs to the host page.
   */
  it('rendered option order matches the input entries array order', () => {
    fc.assert(
      fc.property(sessionEntriesArb({ minLength: 1, maxLength: 30 }), (entries) => {
        cleanup();
        const { container } = render(
          <SessionHistoryPanel {...defaultProps} entries={entries} />,
        );

        const options = container.querySelectorAll('[role="option"]');
        expect(options.length).toBe(entries.length);

        for (let i = 0; i < entries.length; i++) {
          const optionText = options[i]!.textContent ?? '';
          expect(optionText).toContain(entries[i]!.preview);
        }

        cleanup();
      }),
      { numRuns: 100 },
    );
  });
});

// ─── Property 3 ───────────────────────────────────────────────────────────────

describe('Feature: session-history-panels, Property 3: Exactly one entry is marked active or none when null', () => {
  /**
   * **Validates: Requirements 2.5, 5.3, 12.2**
   *
   * For any non-empty array of SessionEntry objects and any activeId that
   * matches one of the entries (or null), the rendered SessionHistoryPanel
   * SHALL have exactly one entry with aria-selected="true" whose data-testid
   * contains the activeId when activeId is not null. When activeId is null,
   * zero entries SHALL have aria-selected="true" and all entries SHALL have
   * aria-selected="false".
   */
  it('exactly one entry has aria-selected="true" matching activeId, or none when null', () => {
    fc.assert(
      fc.property(
        sessionEntriesArb({ minLength: 1, maxLength: 20 }).chain((entries) =>
          fc.tuple(
            fc.constant(entries),
            fc.oneof(
              fc.constant(null),
              fc.constantFrom(...entries.map((e) => e.id)),
            ),
          ),
        ),
        ([entries, activeId]) => {
          cleanup();
          const { container } = render(
            <SessionHistoryPanel {...defaultProps} entries={entries} activeId={activeId} />,
          );

          const options = container.querySelectorAll('[role="option"]');
          expect(options.length).toBe(entries.length);

          const selectedOptions = container.querySelectorAll('[role="option"][aria-selected="true"]');

          if (activeId !== null) {
            // Exactly one entry should be marked active
            expect(selectedOptions.length).toBe(1);
            // That entry's data-testid should contain the activeId
            const selectedEl = selectedOptions[0]!;
            expect(selectedEl.getAttribute('data-testid')).toBe(`session-entry-${activeId}`);
          } else {
            // No entries should be marked active
            expect(selectedOptions.length).toBe(0);
            // All options should have aria-selected="false"
            for (let i = 0; i < options.length; i++) {
              expect(options[i]!.getAttribute('aria-selected')).toBe('false');
            }
          }

          cleanup();
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ─── Property 7 ───────────────────────────────────────────────────────────────

describe('Feature: session-history-panels, Property 7: Toggle collapse is a round-trip and aria-expanded reflects state', () => {
  /**
   * **Validates: Requirements 7.3, 12.1**
   *
   * For any initial collapse state (established by a random number of toggle
   * clicks), clicking the toggle button SHALL invert the collapse state and
   * update aria-expanded to match. Clicking the toggle button a second time
   * SHALL restore the original state. At all times, the aria-expanded attribute
   * on the toggle button SHALL equal the string representation of whether the
   * panel is expanded.
   */
  it('toggling inverts aria-expanded and double-toggle restores original state', () => {
    fc.assert(
      fc.property(
        sessionEntriesArb({ minLength: 1, maxLength: 5 }),
        fc.integer({ min: 0, max: 10 }),
        (entries, initialClicks) => {
          cleanup();
          const { getByTestId } = render(
            <SessionHistoryPanel {...defaultProps} entries={entries} />,
          );

          const toggle = getByTestId('panel-toggle');

          // Component always starts expanded (aria-expanded="true")
          expect(toggle.getAttribute('aria-expanded')).toBe('true');

          // Apply random number of initial clicks to establish a random starting state
          for (let i = 0; i < initialClicks; i++) {
            fireEvent.click(toggle);
          }

          // Step 2: Record the current aria-expanded value
          const stateBeforeToggle = toggle.getAttribute('aria-expanded');

          // Step 3: Click the toggle — assert aria-expanded is inverted
          fireEvent.click(toggle);
          const stateAfterFirstToggle = toggle.getAttribute('aria-expanded');
          const expectedInverted = stateBeforeToggle === 'true' ? 'false' : 'true';
          expect(stateAfterFirstToggle).toBe(expectedInverted);

          // Step 4: Click the toggle again — assert aria-expanded is restored
          fireEvent.click(toggle);
          const stateAfterSecondToggle = toggle.getAttribute('aria-expanded');
          expect(stateAfterSecondToggle).toBe(stateBeforeToggle);

          cleanup();
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ─── Property 8 ───────────────────────────────────────────────────────────────

describe('Feature: session-history-panels, Property 8: Arrow key navigation moves focus correctly', () => {
  /**
   * **Validates: Requirements 12.3**
   *
   * For any list of SessionEntry objects with n > 1 entries and any currently
   * focused entry at index i, pressing ArrowDown SHALL move focus to
   * min(i + 1, n - 1) and pressing ArrowUp SHALL move focus to max(i - 1, 0).
   * The focused entry SHALL receive tabindex="0" and all others SHALL have
   * tabindex="-1".
   */
  it('ArrowDown moves focus to min(i+1, n-1) and ArrowUp moves focus to max(i-1, 0)', () => {
    fc.assert(
      fc.property(
        sessionEntriesArb({ minLength: 2, maxLength: 20 }).chain((entries) =>
          fc.tuple(
            fc.constant(entries),
            fc.integer({ min: 0, max: entries.length - 1 }),
          ),
        ),
        ([entries, startIndex]) => {
          cleanup();
          const n = entries.length;

          const { container } = render(
            <SessionHistoryPanel {...defaultProps} entries={entries} />,
          );

          const listbox = container.querySelector('[role="listbox"]')!;
          expect(listbox).toBeTruthy();

          // Navigate to the starting focus index by pressing ArrowDown from index 0
          for (let i = 0; i < startIndex; i++) {
            fireEvent.keyDown(listbox, { key: 'ArrowDown' });
          }

          // Verify we are at the starting index: entry at startIndex has tabindex="0"
          const optionsBefore = container.querySelectorAll('[role="option"]');
          for (let i = 0; i < n; i++) {
            const expected = i === startIndex ? '0' : '-1';
            expect(optionsBefore[i]!.getAttribute('tabindex')).toBe(expected);
          }

          // ── Test ArrowDown ──
          fireEvent.keyDown(listbox, { key: 'ArrowDown' });
          const expectedDownIndex = Math.min(startIndex + 1, n - 1);

          const optionsAfterDown = container.querySelectorAll('[role="option"]');
          for (let i = 0; i < n; i++) {
            const expected = i === expectedDownIndex ? '0' : '-1';
            expect(optionsAfterDown[i]!.getAttribute('tabindex')).toBe(expected);
          }

          // ── Navigate back to startIndex ──
          // We are now at expectedDownIndex; navigate back to startIndex
          if (expectedDownIndex > startIndex) {
            // We moved down by 1, so press ArrowUp once to go back
            fireEvent.keyDown(listbox, { key: 'ArrowUp' });
          }
          // If expectedDownIndex === startIndex (was already at last), we're still there

          // Verify we're back at startIndex
          const optionsReset = container.querySelectorAll('[role="option"]');
          for (let i = 0; i < n; i++) {
            const expected = i === startIndex ? '0' : '-1';
            expect(optionsReset[i]!.getAttribute('tabindex')).toBe(expected);
          }

          // ── Test ArrowUp ──
          fireEvent.keyDown(listbox, { key: 'ArrowUp' });
          const expectedUpIndex = Math.max(startIndex - 1, 0);

          const optionsAfterUp = container.querySelectorAll('[role="option"]');
          for (let i = 0; i < n; i++) {
            const expected = i === expectedUpIndex ? '0' : '-1';
            expect(optionsAfterUp[i]!.getAttribute('tabindex')).toBe(expected);
          }

          cleanup();
        },
      ),
      { numRuns: 100 },
    );
  });
});


// ─── Property 9 ───────────────────────────────────────────────────────────────

describe('Feature: session-history-panels, Property 9: Focus moves to correct entry after deletion', () => {
  /**
   * **Validates: Requirements 12.4**
   *
   * For any list of SessionEntry objects with n > 1 entries and any deleted
   * entry at index i, after deletion keyboard focus SHALL move to the entry at
   * index min(i, n - 2) — i.e., the next entry, or the previous entry if the
   * last item was removed.
   */
  it('after deletion, tabindex="0" is on the entry at min(deletedIndex, newLength - 1)', () => {
    fc.assert(
      fc.property(
        sessionEntriesArb({ minLength: 2, maxLength: 15 }).chain((entries) =>
          fc.tuple(
            fc.constant(entries),
            fc.integer({ min: 0, max: entries.length - 1 }),
          ),
        ),
        ([entries, deletionIndex]) => {
          cleanup();
          const n = entries.length;

          const { container, rerender } = render(
            <SessionHistoryPanel {...defaultProps} entries={entries} deleteMode="instant" />,
          );

          const listbox = container.querySelector('[role="listbox"]')!;
          expect(listbox).toBeTruthy();

          // Navigate focus to the deletion index by pressing ArrowDown from index 0
          for (let i = 0; i < deletionIndex; i++) {
            fireEvent.keyDown(listbox, { key: 'ArrowDown' });
          }

          // Verify we are at the deletion index
          const optionsBefore = container.querySelectorAll('[role="option"]');
          expect(optionsBefore[deletionIndex]!.getAttribute('tabindex')).toBe('0');

          // Simulate deletion: re-render with the entry at deletionIndex removed
          const entriesAfterDeletion = [
            ...entries.slice(0, deletionIndex),
            ...entries.slice(deletionIndex + 1),
          ];

          // Wrap rerender in act() so the rAF-based state update is flushed
          act(() => {
            rerender(
              <SessionHistoryPanel
                {...defaultProps}
                entries={entriesAfterDeletion}
                deleteMode="instant"
              />,
            );
          });

          // After deletion, the new length is n - 1
          const newLength = n - 1;
          const expectedFocusIndex = Math.min(deletionIndex, newLength - 1);

          // Verify the correct entry has tabindex="0"
          const optionsAfter = container.querySelectorAll('[role="option"]');
          expect(optionsAfter.length).toBe(newLength);

          for (let i = 0; i < newLength; i++) {
            const expected = i === expectedFocusIndex ? '0' : '-1';
            expect(optionsAfter[i]!.getAttribute('tabindex')).toBe(expected);
          }

          cleanup();
        },
      ),
      { numRuns: 100 },
    );
  });
});


// ─── Property 4 ───────────────────────────────────────────────────────────────

describe('Feature: session-history-panels, Property 4: Removing an entry preserves all other entries in order', () => {
  /**
   * **Validates: Requirements 3.4, 6.2, 9.5**
   *
   * For any array of SessionEntry objects with unique IDs and any entry ID to
   * remove, after calling removeEntry the resulting list SHALL not contain the
   * removed ID, SHALL contain all other entries, and SHALL preserve their
   * relative order. If the ID is not present, the result SHALL equal the
   * original array.
   */
  it('removed ID is absent, all others present in order, length is original - 1', () => {
    fc.assert(
      fc.property(
        sessionEntriesArb({ minLength: 1, maxLength: 30 }).chain((entries) =>
          fc.tuple(
            fc.constant(entries),
            fc.constantFrom(...entries.map((e) => e.id)),
          ),
        ),
        ([entries, idToRemove]) => {
          const result = removeEntry(entries, idToRemove);

          // Removed ID is not in the result
          expect(result.find((e) => e.id === idToRemove)).toBeUndefined();

          // Result length is original - 1
          expect(result.length).toBe(entries.length - 1);

          // All other entries are present
          const expected = entries.filter((e) => e.id !== idToRemove);
          expect(result.map((e) => e.id)).toEqual(expected.map((e) => e.id));

          // Relative order is preserved (already checked by toEqual above,
          // but let's be explicit about pairwise ordering)
          for (let i = 1; i < result.length; i++) {
            const prevOrigIdx = entries.findIndex((e) => e.id === result[i - 1]!.id);
            const currOrigIdx = entries.findIndex((e) => e.id === result[i]!.id);
            expect(prevOrigIdx).toBeLessThan(currOrigIdx);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('removing an ID not in the array returns the original entries unchanged', () => {
    fc.assert(
      fc.property(
        sessionEntriesArb({ minLength: 1, maxLength: 30 }),
        fc.uuid(),
        (entries, missingId) => {
          // Ensure missingId is not in the entries
          fc.pre(!entries.some((e) => e.id === missingId));

          const result = removeEntry(entries, missingId);

          // Result should equal the original
          expect(result.length).toBe(entries.length);
          expect(result.map((e) => e.id)).toEqual(entries.map((e) => e.id));
        },
      ),
      { numRuns: 100 },
    );
  });
});


// ─── Property 5 ───────────────────────────────────────────────────────────────

describe('Feature: session-history-panels, Property 5: Upsert places session at top of list', () => {
  /**
   * **Validates: Requirements 9.2**
   *
   * For any array of SessionEntry objects and any session to upsert (either an
   * existing ID with updated date or a new ID), after upserting the resulting
   * list SHALL have the upserted session at index 0. If the session already
   * existed, the list length SHALL remain the same and the old entry SHALL be
   * removed from its previous position. If the session is new, the list length
   * SHALL increase by 1.
   */

  it('upserting an existing entry places it at index 0 with updated data, preserving length and relative order of others', () => {
    fc.assert(
      fc.property(
        sessionEntriesArb({ minLength: 1, maxLength: 30 }).chain((entries) =>
          fc.tuple(
            fc.constant(entries),
            fc.integer({ min: 0, max: entries.length - 1 }),
            previewArb,
            isoDateArb,
          ),
        ),
        ([entries, targetIndex, newPreview, newDate]) => {
          const existingEntry = entries[targetIndex]!;
          const updatedEntry: SessionEntry = {
            id: existingEntry.id,
            preview: newPreview,
            date: newDate,
          };

          const result = upsertEntry(entries, updatedEntry);

          // Upserted entry is at index 0 with updated data
          expect(result[0]).toEqual(updatedEntry);

          // Length unchanged (existing entry was replaced, not added)
          expect(result.length).toBe(entries.length);

          // Old version is gone — no other entry has the same id
          const matchingIds = result.filter((e) => e.id === existingEntry.id);
          expect(matchingIds.length).toBe(1);
          expect(matchingIds[0]).toEqual(updatedEntry);

          // All other entries maintain their relative order
          const othersResult = result.slice(1);
          const othersOriginal = entries.filter((e) => e.id !== existingEntry.id);
          expect(othersResult.map((e) => e.id)).toEqual(othersOriginal.map((e) => e.id));
        },
      ),
      { numRuns: 100 },
    );
  });

  it('upserting a new entry places it at index 0, increases length by 1, and preserves all original entries in order', () => {
    fc.assert(
      fc.property(
        sessionEntriesArb({ minLength: 0, maxLength: 30 }),
        sessionEntryArb,
        (entries, newEntry) => {
          // Ensure the new entry's ID is not already in the array
          fc.pre(!entries.some((e) => e.id === newEntry.id));

          const result = upsertEntry(entries, newEntry);

          // New entry is at index 0
          expect(result[0]).toEqual(newEntry);

          // Length is original + 1
          expect(result.length).toBe(entries.length + 1);

          // All original entries are present and maintain relative order
          const remaining = result.slice(1);
          expect(remaining.map((e) => e.id)).toEqual(entries.map((e) => e.id));
          for (let i = 0; i < entries.length; i++) {
            expect(remaining[i]).toEqual(entries[i]);
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});


// ─── Property 6 ───────────────────────────────────────────────────────────────

describe('Feature: session-history-panels, Property 6: Prepend places new entry at index 0', () => {
  /**
   * **Validates: Requirements 9.3**
   *
   * For any array of SessionEntry objects and any new SessionEntry, after
   * prepending the resulting list SHALL have the new entry at index 0 and the
   * list length SHALL be the original length plus 1. All previous entries SHALL
   * maintain their relative order.
   */
  it('prepended entry is at index 0, length is original + 1, and previous entries maintain order', () => {
    fc.assert(
      fc.property(
        sessionEntriesArb({ minLength: 0, maxLength: 30 }),
        sessionEntryArb,
        (entries, newEntry) => {
          const result = prependEntry(entries, newEntry);

          // New entry is at index 0
          expect(result[0]).toEqual(newEntry);

          // Length is original + 1
          expect(result.length).toBe(entries.length + 1);

          // All previous entries maintain their relative order
          const remaining = result.slice(1);
          expect(remaining).toEqual(entries);
        },
      ),
      { numRuns: 100 },
    );
  });
});
