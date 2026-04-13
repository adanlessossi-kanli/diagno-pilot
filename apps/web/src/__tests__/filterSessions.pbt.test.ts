// Feature: ux-improvements, Property 6: Session entry search filter correctness
// **Validates: Requirements 6.2**

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import type { SessionEntry } from '../components/SessionHistoryPanel';
import { filterEntriesByPreview } from '../components/SessionHistoryPanel';

const sessionEntryArb: fc.Arbitrary<SessionEntry> = fc.record({
  id: fc.string(),
  preview: fc.string(),
  date: fc.date().map((d) => d.toISOString()),
});

describe('P6: Session entry search filter correctness', () => {
  it('returns the full input list when query is empty or whitespace-only', () => {
    // Feature: ux-improvements, Property 6: Session entry search filter correctness
    fc.assert(
      fc.property(
        fc.array(sessionEntryArb),
        fc.array(fc.constantFrom(' ', '\t', '\n', '\r')).map((chars) => chars.join('')),
        (entries, whitespaceQuery) => {
          expect(filterEntriesByPreview(entries, whitespaceQuery)).toEqual(entries);
          expect(filterEntriesByPreview(entries, '')).toEqual(entries);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('returns only entries whose preview contains the query as a case-insensitive substring', () => {
    // Feature: ux-improvements, Property 6: Session entry search filter correctness
    fc.assert(
      fc.property(
        fc.array(sessionEntryArb),
        fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0),
        (entries, query) => {
          const result = filterEntriesByPreview(entries, query);
          const lowerQuery = query.trim().toLowerCase();
          for (const e of result) {
            expect(e.preview.toLowerCase()).toContain(lowerQuery);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('result is always a subset of the original list, preserving order', () => {
    // Feature: ux-improvements, Property 6: Session entry search filter correctness
    fc.assert(
      fc.property(
        fc.array(sessionEntryArb),
        fc.string(),
        (entries, query) => {
          const result = filterEntriesByPreview(entries, query);
          // Every result element must be in the original list
          for (const e of result) {
            expect(entries).toContain(e);
          }
          // Result length must not exceed original
          expect(result.length).toBeLessThanOrEqual(entries.length);
          // Order is preserved: indices in original list must be strictly increasing
          const indices = result.map((e) => entries.indexOf(e));
          for (let i = 1; i < indices.length; i++) {
            expect(indices[i]).toBeGreaterThan(indices[i - 1]);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('returns an empty array when the input list is empty, regardless of query', () => {
    // Feature: ux-improvements, Property 6: Session entry search filter correctness
    fc.assert(
      fc.property(
        fc.string(),
        (query) => {
          expect(filterEntriesByPreview([], query)).toEqual([]);
        },
      ),
      { numRuns: 100 },
    );
  });
});
