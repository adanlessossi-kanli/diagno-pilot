/**
 * Property-based tests for the IMAGES registry.
 *
 * Feature: diagno-pilot-improvements, Property 20: Attribut alt présent sur toutes les images
 *
 * **Validates: Requirements 16.6**
 */
import fc from 'fast-check';
import { IMAGES } from '../images';

// P20 — Attribut alt présent sur toutes les images
describe('IMAGES registry', () => {
  it('P20 — every image entry has a non-empty src and a non-empty alt', () => {
    const entries = Object.entries(IMAGES) as [string, { src: string; alt: string }][];

    // Verify statically that every known entry satisfies the property
    for (const [key, value] of entries) {
      expect(value.src, `${key}.src should be non-empty`).toBeTruthy();
      expect(value.alt, `${key}.alt should be non-empty`).toBeTruthy();
    }

    // Property: for any key drawn from the IMAGES object, alt is a non-empty string
    fc.assert(
      fc.property(
        fc.constantFrom(...(Object.keys(IMAGES) as (keyof typeof IMAGES)[])),
        (key) => {
          const entry = IMAGES[key];
          return (
            typeof entry.alt === 'string' &&
            entry.alt.trim().length > 0 &&
            typeof entry.src === 'string' &&
            entry.src.trim().length > 0
          );
        }
      ),
      { numRuns: 100 }
    );
  });
});
