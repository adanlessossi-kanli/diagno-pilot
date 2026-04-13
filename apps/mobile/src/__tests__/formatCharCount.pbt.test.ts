// Feature: ux-improvements, Property 2: Character count formatting
// **Validates: Requirements 3.2**

import fc from 'fast-check';
import { formatCharCount } from '../utils/formatCharCount';

describe('P2: Character count formatting', () => {
  it('returns "{current}/{max}" for any non-negative current and positive max', () => {
    // Feature: ux-improvements, Property 2: Character count formatting
    fc.assert(
      fc.property(
        fc.nat({ max: 10000 }),
        fc.integer({ min: 1, max: 10000 }),
        (current, max) => {
          const result = formatCharCount(current, max);
          expect(result).toBe(`${current}/${max}`);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('contains exactly one "/" separator', () => {
    // Feature: ux-improvements, Property 2: Character count formatting
    fc.assert(
      fc.property(
        fc.nat({ max: 10000 }),
        fc.integer({ min: 1, max: 10000 }),
        (current, max) => {
          const result = formatCharCount(current, max);
          const slashes = result.split('/');
          expect(slashes).toHaveLength(2);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('parses back to the original numbers', () => {
    // Feature: ux-improvements, Property 2: Character count formatting
    fc.assert(
      fc.property(
        fc.nat({ max: 10000 }),
        fc.integer({ min: 1, max: 10000 }),
        (current, max) => {
          const result = formatCharCount(current, max);
          const [parsedCurrent, parsedMax] = result.split('/').map(Number);
          expect(parsedCurrent).toBe(current);
          expect(parsedMax).toBe(max);
        },
      ),
      { numRuns: 100 },
    );
  });
});
