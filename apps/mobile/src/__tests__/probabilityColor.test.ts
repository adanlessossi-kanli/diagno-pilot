// Feature: ui-professional-refactor, Property 12: Mobile diagnosis card probability color mapping
// **Validates: Requirements 12.4**
import fc from 'fast-check';
import { getProbabilityColor } from '../utils/probabilityColor';
import { colors } from '@diagno-pilot/ui/src/tokens';

describe('getProbabilityColor', () => {
  it('P12: returns green border token for p >= 0.7', () => {
    fc.assert(
      fc.property(fc.double({ min: 0.7, max: 1, noNaN: true }), (p) => {
        expect(getProbabilityColor(p)).toBe(colors.success.border);
      }),
      { numRuns: 100 }
    );
  });

  it('P12: returns amber/warning border token for 0.4 <= p < 0.7', () => {
    fc.assert(
      fc.property(fc.double({ min: 0.4, max: 0.6999999999999999, noNaN: true }), (p) => {
        expect(getProbabilityColor(p)).toBe(colors.warning.border);
      }),
      { numRuns: 100 }
    );
  });

  it('P12: returns red/error border token for p < 0.4', () => {
    fc.assert(
      fc.property(fc.double({ min: 0, max: 0.3999999999999999, noNaN: true }), (p) => {
        expect(getProbabilityColor(p)).toBe(colors.error.border);
      }),
      { numRuns: 100 }
    );
  });

  // Boundary tests
  it('returns green at exactly 0.7', () => {
    expect(getProbabilityColor(0.7)).toBe(colors.success.border);
  });

  it('returns amber at exactly 0.4', () => {
    expect(getProbabilityColor(0.4)).toBe(colors.warning.border);
  });

  it('returns red at exactly 0', () => {
    expect(getProbabilityColor(0)).toBe(colors.error.border);
  });
});
