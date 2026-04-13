// Feature: ux-improvements, Property 4: PrescriptionCard renders provided labels
// **Validates: Requirements 5.2**

import React from 'react';
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import * as fc from 'fast-check';
import { PrescriptionCard } from '../PrescriptionCard';
import type { Prescription } from '@diagno-pilot/types';

function makePrescription(overrides: Partial<Prescription> = {}): Prescription {
  return {
    antibiotic: 'Amoxicillin',
    doseMg: 500,
    frequency: '3x/day',
    durationDays: 7,
    route: 'oral' as const,
    isCappedToAdultDose: false,
    ...overrides,
  };
}

// Arbitrary that generates non-empty printable label strings (no HTML-special chars)
const labelArb = fc.string({ minLength: 2, maxLength: 30 }).filter((s) => {
  const trimmed = s.trim();
  return trimmed.length >= 2 && !/[<>&"]/.test(trimmed);
});

describe('P4: PrescriptionCard renders provided labels', () => {
  it('renders all provided label strings in the output', () => {
    // Feature: ux-improvements, Property 4: PrescriptionCard renders provided labels
    fc.assert(
      fc.property(
        fc.record({
          dose: labelArb,
          frequency: labelArb,
          duration: labelArb,
          route: labelArb,
        }),
        (labels) => {
          const rx = makePrescription();
          const { container } = render(
            <PrescriptionCard prescription={rx} labels={labels} />,
          );
          const text = container.textContent ?? '';

          expect(text).toContain(labels.dose);
          expect(text).toContain(labels.frequency);
          expect(text).toContain(labels.duration);
          expect(text).toContain(labels.route);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('renders cappedToAdultDose label when isCappedToAdultDose is true', () => {
    // Feature: ux-improvements, Property 4: PrescriptionCard renders provided labels
    fc.assert(
      fc.property(
        labelArb,
        (cappedLabel) => {
          const rx = makePrescription({ isCappedToAdultDose: true });
          const { container } = render(
            <PrescriptionCard prescription={rx} labels={{ cappedToAdultDose: cappedLabel }} />,
          );
          const text = container.textContent ?? '';
          expect(text).toContain(cappedLabel);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('falls back to default English labels when labels prop is omitted', () => {
    // Feature: ux-improvements, Property 4: PrescriptionCard renders provided labels
    const rx = makePrescription();
    const { container } = render(<PrescriptionCard prescription={rx} />);
    const text = container.textContent ?? '';

    expect(text).toContain('Dose');
    expect(text).toContain('Frequency');
    expect(text).toContain('Duration');
    expect(text).toContain('Route');
  });

  it('falls back to default cappedToAdultDose label when not provided', () => {
    // Feature: ux-improvements, Property 4: PrescriptionCard renders provided labels
    const rx = makePrescription({ isCappedToAdultDose: true });
    const { container } = render(<PrescriptionCard prescription={rx} />);
    const text = container.textContent ?? '';
    expect(text).toContain('Capped to adult dose');
  });
});
