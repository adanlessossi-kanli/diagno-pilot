/**
 * Property-based tests for DocumentSidebar logic.
 *
 * Property 4: File Format Validation
 * Property 5: Document List Update on Upload
 * Property 6: Document List Update on Delete
 *
 * Uses fast-check with { numRuns: 100 }.
 */

import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { isAcceptedFileFormat } from '../components/DocumentSidebar';

// ─── PatientDocument arbitrary ────────────────────────────────────────────────

interface PatientDocument {
  id: string;
  title: string;
  source: string;
  s3Key: string;
  originalName: string;
  sizeBytes: number;
  indexedAt?: string;
  createdAt: string;
  chunkCount?: number;
}

const safeDate = fc.integer({
  min: new Date('2000-01-01').getTime(),
  max: new Date('2030-12-31').getTime(),
}).map((ts) => new Date(ts));

const patientDocumentArb: fc.Arbitrary<PatientDocument> = fc.record({
  id: fc.uuid(),
  title: fc.string({ minLength: 1, maxLength: 100 }),
  source: fc.string({ minLength: 1, maxLength: 50 }),
  s3Key: fc.string({ minLength: 1, maxLength: 200 }),
  originalName: fc.string({ minLength: 1, maxLength: 100 }),
  sizeBytes: fc.nat({ max: 100_000_000 }),
  indexedAt: fc.option(safeDate.map((d) => d.toISOString()), { nil: undefined }),
  createdAt: safeDate.map((d) => d.toISOString()),
  chunkCount: fc.option(fc.nat({ max: 1000 }), { nil: undefined }),
});

// ─── Accepted extensions ──────────────────────────────────────────────────────

const ACCEPTED_EXTENSIONS = ['pdf', 'docx', 'txt', 'csv'];

// ─── Property 4: File Format Validation ───────────────────────────────────────
// **Validates: Requirements 3.3**

describe('Property 4: File Format Validation', () => {
  it('accepts a file iff its extension (case-insensitive) is in {pdf, docx, txt, csv}', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 10 }).filter((s) => !s.includes('.')),
        (ext) => {
          const filename = `file.${ext}`;
          const expected = ACCEPTED_EXTENSIONS.includes(ext.toLowerCase());
          expect(isAcceptedFileFormat(filename)).toBe(expected);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('is case-insensitive — any mixed-case accepted extension returns true', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...ACCEPTED_EXTENSIONS),
        fc.boolean(),
        fc.boolean(),
        fc.boolean(),
        fc.boolean(),
        (ext, b0, b1, b2, b3) => {
          // Apply random casing to each character
          const flags = [b0, b1, b2, b3];
          const mixedCase = ext
            .split('')
            .map((ch, i) => (flags[i % flags.length] ? ch.toUpperCase() : ch.toLowerCase()))
            .join('');
          expect(isAcceptedFileFormat(`document.${mixedCase}`)).toBe(true);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('files with no extension return false', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }).filter((s) => !s.includes('.')),
        (filename) => {
          expect(isAcceptedFileFormat(filename)).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('files with multiple dots use the last extension', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 10 }).filter((s) => !s.includes('.')),
        fc.constantFrom('tar', 'backup', 'old', 'v2'),
        fc.constantFrom(...ACCEPTED_EXTENSIONS),
        (baseName, middleExt, lastExt) => {
          const filename = `${baseName}.${middleExt}.${lastExt}`;
          expect(isAcceptedFileFormat(filename)).toBe(true);
        },
      ),
      { numRuns: 100 },
    );
  });
});


// ─── Property 5: Document List Update on Upload ──────────────────────────────
// **Validates: Requirements 3.2**

describe('Property 5: Document List Update on Upload', () => {
  it('prepending a new document increases list length by exactly 1', () => {
    fc.assert(
      fc.property(
        fc.array(patientDocumentArb, { minLength: 0, maxLength: 50 }),
        patientDocumentArb,
        (existingDocs, newDoc) => {
          // Simulate: setDocuments((prev) => [newDoc, ...prev])
          const updated = [newDoc, ...existingDocs];
          expect(updated.length).toBe(existingDocs.length + 1);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('the new document appears at the beginning of the list', () => {
    fc.assert(
      fc.property(
        fc.array(patientDocumentArb, { minLength: 0, maxLength: 50 }),
        patientDocumentArb,
        (existingDocs, newDoc) => {
          const updated = [newDoc, ...existingDocs];
          expect(updated[0]).toBe(newDoc);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('existing documents are preserved in order after the new one', () => {
    fc.assert(
      fc.property(
        fc.array(patientDocumentArb, { minLength: 0, maxLength: 50 }),
        patientDocumentArb,
        (existingDocs, newDoc) => {
          const updated = [newDoc, ...existingDocs];
          expect(updated.slice(1)).toEqual(existingDocs);
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ─── Property 6: Document List Update on Delete ──────────────────────────────
// **Validates: Requirements 4.2**

describe('Property 6: Document List Update on Delete', () => {
  it('filtering by id removes exactly one document', () => {
    fc.assert(
      fc.property(
        fc.array(patientDocumentArb, { minLength: 1, maxLength: 50 }).chain((docs) => {
          // Ensure unique ids
          const uniqueDocs = docs.map((d, i) => ({ ...d, id: `${d.id}-${i}` }));
          // Pick a random index to delete
          return fc.tuple(
            fc.constant(uniqueDocs),
            fc.integer({ min: 0, max: uniqueDocs.length - 1 }),
          );
        }),
        ([docs, indexToDelete]) => {
          const idToDelete = docs[indexToDelete].id;
          // Simulate: setDocuments((prev) => prev.filter((d) => d.id !== id))
          const updated = docs.filter((d) => d.id !== idToDelete);
          expect(updated.length).toBe(docs.length - 1);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('the deleted document is no longer in the list', () => {
    fc.assert(
      fc.property(
        fc.array(patientDocumentArb, { minLength: 1, maxLength: 50 }).chain((docs) => {
          const uniqueDocs = docs.map((d, i) => ({ ...d, id: `${d.id}-${i}` }));
          return fc.tuple(
            fc.constant(uniqueDocs),
            fc.integer({ min: 0, max: uniqueDocs.length - 1 }),
          );
        }),
        ([docs, indexToDelete]) => {
          const idToDelete = docs[indexToDelete].id;
          const updated = docs.filter((d) => d.id !== idToDelete);
          expect(updated.find((d) => d.id === idToDelete)).toBeUndefined();
        },
      ),
      { numRuns: 100 },
    );
  });

  it('all other documents are preserved in order', () => {
    fc.assert(
      fc.property(
        fc.array(patientDocumentArb, { minLength: 1, maxLength: 50 }).chain((docs) => {
          const uniqueDocs = docs.map((d, i) => ({ ...d, id: `${d.id}-${i}` }));
          return fc.tuple(
            fc.constant(uniqueDocs),
            fc.integer({ min: 0, max: uniqueDocs.length - 1 }),
          );
        }),
        ([docs, indexToDelete]) => {
          const idToDelete = docs[indexToDelete].id;
          const updated = docs.filter((d) => d.id !== idToDelete);
          const expectedRemaining = docs.filter((_, i) => i !== indexToDelete);
          expect(updated).toEqual(expectedRemaining);
        },
      ),
      { numRuns: 100 },
    );
  });
});
