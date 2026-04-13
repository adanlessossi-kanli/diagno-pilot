// Feature: ux-improvements, Property 7: Error message completeness
// **Validates: Requirements 8.1**

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { buildErrorMessage, ERROR_TYPES } from '../utils/errorMessages';

describe('P7: Error message completeness', () => {
  it('returns non-empty descriptionKey and actionKey for every known error type', () => {
    // Feature: ux-improvements, Property 7: Error message completeness
    fc.assert(
      fc.property(
        fc.constantFrom(...ERROR_TYPES),
        (errorType) => {
          const result = buildErrorMessage(errorType);
          expect(result.descriptionKey).toBeTruthy();
          expect(result.actionKey).toBeTruthy();
          expect(typeof result.descriptionKey).toBe('string');
          expect(typeof result.actionKey).toBe('string');
          expect(result.descriptionKey.length).toBeGreaterThan(0);
          expect(result.actionKey.length).toBeGreaterThan(0);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('returns keys that look like valid i18n translation keys (dot-separated)', () => {
    // Feature: ux-improvements, Property 7: Error message completeness
    fc.assert(
      fc.property(
        fc.constantFrom(...ERROR_TYPES),
        (errorType) => {
          const result = buildErrorMessage(errorType);
          expect(result.descriptionKey).toMatch(/^[a-z]+\.[a-zA-Z]+$/);
          expect(result.actionKey).toMatch(/^[a-z]+\.[a-zA-Z]+$/);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('falls back to generic error for unknown error types', () => {
    // Feature: ux-improvements, Property 7: Error message completeness
    fc.assert(
      fc.property(
        fc.string({ minLength: 1 }).filter((s) => !ERROR_TYPES.includes(s as any)),
        (unknownType) => {
          const result = buildErrorMessage(unknownType);
          const generic = buildErrorMessage('generic');
          expect(result).toEqual(generic);
          expect(result.descriptionKey.length).toBeGreaterThan(0);
          expect(result.actionKey.length).toBeGreaterThan(0);
        },
      ),
      { numRuns: 100 },
    );
  });
});
