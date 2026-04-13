// Feature: ux-improvements, Property 1: Step progress state mapping
// **Validates: Requirements 2.1**

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { getStepState } from '../StepProgress';

describe('P1: Step progress state mapping', () => {
  it('returns "completed" for steps before the current index', () => {
    // Feature: ux-improvements, Property 1: Step progress state mapping
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 100 }),
        (currentIndex) => {
          for (let i = 0; i < currentIndex; i++) {
            expect(getStepState(i, currentIndex)).toBe('completed');
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('returns "current" for the step at the current index', () => {
    // Feature: ux-improvements, Property 1: Step progress state mapping
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 100 }),
        (currentIndex) => {
          expect(getStepState(currentIndex, currentIndex)).toBe('current');
        },
      ),
      { numRuns: 100 },
    );
  });

  it('returns "upcoming" for steps after the current index', () => {
    // Feature: ux-improvements, Property 1: Step progress state mapping
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 99 }),
        fc.integer({ min: 1, max: 50 }),
        (currentIndex, offset) => {
          const stepIndex = currentIndex + offset;
          expect(getStepState(stepIndex, currentIndex)).toBe('upcoming');
        },
      ),
      { numRuns: 100 },
    );
  });

  it('correctly maps all steps for any N >= 1 and valid current index', () => {
    // Feature: ux-improvements, Property 1: Step progress state mapping
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 20 }).chain((n) =>
          fc.tuple(fc.constant(n), fc.integer({ min: 0, max: n - 1 })),
        ),
        ([n, currentIndex]) => {
          for (let i = 0; i < n; i++) {
            const state = getStepState(i, currentIndex);
            if (i < currentIndex) {
              expect(state).toBe('completed');
            } else if (i === currentIndex) {
              expect(state).toBe('current');
            } else {
              expect(state).toBe('upcoming');
            }
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});
