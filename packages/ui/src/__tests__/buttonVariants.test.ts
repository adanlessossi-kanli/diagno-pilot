import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { buttonVariants } from '../buttonVariants';

// Feature: ui-professional-refactor, Property 6: Button variant visual correctness
// For each variant × state combination, the class string contains the expected tokens.

type Variant = keyof typeof buttonVariants;

const variantArb = fc.oneof(
  fc.constant('primary' as const),
  fc.constant('secondary' as const),
  fc.constant('ghost' as const),
);

describe('P6: Button variant visual correctness', () => {
  it('each variant contains the correct visual token classes', () => {
    // Feature: ui-professional-refactor, Property 6: Button variant visual correctness
    fc.assert(
      fc.property(variantArb, (variant) => {
        const classes = buttonVariants[variant];

        if (variant === 'primary') {
          // Filled background using primary color token
          expect(classes).toContain('bg-primary-600');
          expect(classes).toContain('text-white');
        }

        if (variant === 'secondary') {
          // Outlined: has a border, no filled primary bg
          expect(classes).toContain('border');
          expect(classes).not.toContain('bg-primary');
        }

        if (variant === 'ghost') {
          // Text-only: no background, no border
          expect(classes).not.toContain('bg-primary');
          expect(classes).not.toContain('bg-neutral');
          expect(classes).not.toContain('border');
        }
      }),
      { numRuns: 100 },
    );
  });

  it('primary variant includes disabled opacity and cursor-not-allowed', () => {
    // disabled state: opacity ≤ 50% and cursor-not-allowed
    expect(buttonVariants.primary).toContain('disabled:opacity-50');
    expect(buttonVariants.primary).toContain('disabled:cursor-not-allowed');
  });

  it('all variants include transition-colors for smooth state changes', () => {
    fc.assert(
      fc.property(variantArb, (variant) => {
        expect(buttonVariants[variant]).toContain('transition-colors');
      }),
      { numRuns: 100 },
    );
  });

  it('primary and secondary variants include rounded-md border radius', () => {
    fc.assert(
      fc.property(
        fc.oneof(fc.constant('primary' as const), fc.constant('secondary' as const)),
        (variant) => {
          expect(buttonVariants[variant]).toContain('rounded-md');
        },
      ),
      { numRuns: 100 },
    );
  });

  it('primary variant has hover state for primary-700', () => {
    expect(buttonVariants.primary).toContain('hover:bg-primary-700');
  });

  it('secondary variant has hover state using neutral token', () => {
    expect(buttonVariants.secondary).toContain('hover:bg-neutral-50');
  });

  it('ghost variant has primary color text', () => {
    expect(buttonVariants.ghost).toContain('text-primary-600');
  });
});
