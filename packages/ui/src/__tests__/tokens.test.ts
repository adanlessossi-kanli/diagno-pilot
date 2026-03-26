import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { colors, typography, spacing } from '../tokens';

// ─── Property 1: Semantic token completeness ──────────────────────────────────
// Feature: ui-professional-refactor, Property 1: For each semantic category in
// {success, warning, error, info}, bg/border/text sub-keys are non-empty strings.

describe('P1: Semantic token completeness', () => {
  it('every semantic category exposes non-empty bg, border, and text strings', () => {
    const semanticCategories = ['success', 'warning', 'error', 'info'] as const;

    fc.assert(
      fc.property(fc.constantFrom(...semanticCategories), (category) => {
        const token = colors[category];
        expect(typeof token.bg).toBe('string');
        expect(token.bg.length).toBeGreaterThan(0);
        expect(typeof token.border).toBe('string');
        expect(token.border.length).toBeGreaterThan(0);
        expect(typeof token.text).toBe('string');
        expect(token.text.length).toBeGreaterThan(0);
      }),
      { numRuns: 100 },
    );
  });
});

// ─── Property 2: Typography values within specified ranges ────────────────────
// Feature: ui-professional-refactor, Property 2: Each named typography size falls
// within its design-specified range: xs∈[11,12], sm∈[13,14], base∈[15,16], lg∈[18,20].

describe('P2: Typography values within specified ranges', () => {
  it('each typography size is within its design-specified range', () => {
    const ranges: Record<keyof typeof typography, [number, number]> = {
      xs:   [11, 12],
      sm:   [13, 14],
      base: [15, 16],
      lg:   [18, 20],
    };

    const sizeKeys = Object.keys(ranges) as Array<keyof typeof typography>;

    fc.assert(
      fc.property(fc.constantFrom(...sizeKeys), (key) => {
        const value = typography[key];
        const [min, max] = ranges[key];
        expect(value).toBeGreaterThanOrEqual(min);
        expect(value).toBeLessThanOrEqual(max);
      }),
      { numRuns: 100 },
    );
  });
});

// ─── Property 3: Spacing values are multiples of 4 ───────────────────────────
// Feature: ui-professional-refactor, Property 3: Every spacing token value is
// divisible by 4 with no remainder.

describe('P3: Spacing values are multiples of 4', () => {
  it('every spacing value is a multiple of 4', () => {
    const spacingValues = Object.values(spacing);

    fc.assert(
      fc.property(fc.constantFrom(...spacingValues), (value) => {
        expect(value % 4).toBe(0);
      }),
      { numRuns: 100 },
    );
  });
});

// ─── Property 4: WCAG contrast ratio compliance ───────────────────────────────
// Feature: ui-professional-refactor, Property 4: For any semantic (foreground,
// background) pair, the WCAG 2.1 contrast ratio is ≥ 4.5:1 for normal text.

/** Parse a 6-digit hex color string to [r, g, b] in [0, 255]. */
function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace('#', '');
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return [r, g, b];
}

/** Relative luminance per WCAG 2.1 §1.4.3. */
function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map((c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2.1 contrast ratio between two hex colors. */
function contrastRatio(hex1: string, hex2: string): number {
  const l1 = relativeLuminance(hex1);
  const l2 = relativeLuminance(hex2);
  const lighter = Math.max(l1, l2);
  const darker  = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

describe('P4: WCAG contrast ratio compliance', () => {
  it('semantic text-on-bg pairs meet ≥ 4.5:1 contrast ratio', () => {
    const semanticCategories = ['success', 'warning', 'error', 'info'] as const;

    fc.assert(
      fc.property(fc.constantFrom(...semanticCategories), (category) => {
        const token = colors[category];
        const ratio = contrastRatio(token.text, token.bg);
        expect(ratio).toBeGreaterThanOrEqual(4.5);
      }),
      { numRuns: 100 },
    );
  });

  it('primary-600 on white meets ≥ 4.5:1 contrast ratio', () => {
    const ratio = contrastRatio(colors.primary[600], '#FFFFFF');
    expect(ratio).toBeGreaterThanOrEqual(4.5);
  });
});
