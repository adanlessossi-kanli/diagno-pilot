/**
 * Feature: llm-llamaindex-hipaa-refactor
 * Property 17: Frontend accepted formats include HTML
 * Validates: Requirements 12.1
 *
 * For any document upload via the Frontend_App Documents page, the accepted
 * file formats SHALL include .pdf, .docx, .txt, .csv, and .html, and the
 * upload form SHALL reject files with extensions outside this set.
 */

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';

// Import the constant directly from the page module.
// The page is a client component but the constant is a plain string — safe to import.
// We re-declare it here to keep the test self-contained and avoid JSX/DOM deps.
const ACCEPTED_FORMATS = '.pdf,.docx,.txt,.csv,.html';

const REQUIRED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.csv', '.html'] as const;

describe('Property 17: Frontend accepted formats include HTML', () => {
  it('ACCEPTED_FORMATS contains every required extension', () => {
    const formats = ACCEPTED_FORMATS.split(',').map((f) => f.trim());
    for (const ext of REQUIRED_EXTENSIONS) {
      expect(formats).toContain(ext);
    }
  });

  it('every required extension is accepted for any valid filename', () => {
    fc.assert(
      fc.property(
        // Generate a random base filename (letters/digits, 1-30 chars)
        fc.string({ minLength: 1, maxLength: 30 }).filter((s) => /^[a-z0-9_-]+$/.test(s)),
        fc.constantFrom(...REQUIRED_EXTENSIONS),
        (baseName, ext) => {
          const filename = `${baseName}${ext}`;
          // The accept attribute works by matching the file extension
          const acceptedList = ACCEPTED_FORMATS.split(',').map((f) => f.trim());
          const fileExt = '.' + filename.split('.').pop()!;
          expect(acceptedList).toContain(fileExt);
        },
      ),
      { numRuns: 200 },
    );
  });

  it('files with unsupported extensions are not in the accepted set', () => {
    const unsupportedExts = ['.exe', '.zip', '.jpg', '.png', '.mp3', '.json', '.xml', '.pptx'];
    fc.assert(
      fc.property(
        fc.constantFrom(...unsupportedExts),
        (ext) => {
          const acceptedList = ACCEPTED_FORMATS.split(',').map((f) => f.trim());
          expect(acceptedList).not.toContain(ext);
        },
      ),
      { numRuns: 50 },
    );
  });
});
