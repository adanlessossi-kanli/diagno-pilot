// Feature: ux-improvements, Property 5: PatientCard renders provided labels
// **Validates: Requirements 5.3**

import React from 'react';
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import * as fc from 'fast-check';
import { PatientCard } from '../PatientCard';
import type { PatientProfile } from '@diagno-pilot/types';

function makePatient(overrides: Partial<PatientProfile> = {}): PatientProfile {
  return {
    allergies: [],
    renalFailure: false,
    hepaticFailure: false,
    currentMedications: [],
    ...overrides,
  };
}

// Arbitrary that generates non-empty printable label strings (no HTML-special chars)
const labelArb = fc.string({ minLength: 2, maxLength: 30 }).filter((s) => {
  const trimmed = s.trim();
  return trimmed.length >= 2 && !/[<>&"]/.test(trimmed);
});

describe('P5: PatientCard renders provided labels', () => {
  it('renders allergies label for any patient (allergies field is always present)', () => {
    // Feature: ux-improvements, Property 5: PatientCard renders provided labels
    fc.assert(
      fc.property(
        labelArb,
        (allergiesLabel) => {
          const patient = makePatient({ fullName: 'Test User' });
          const { container } = render(
            <PatientCard patient={patient} labels={{ allergies: allergiesLabel }} />,
          );
          const text = container.textContent ?? '';
          expect(text).toContain(allergiesLabel);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('renders weight label only when weightKg is defined', () => {
    // Feature: ux-improvements, Property 5: PatientCard renders provided labels
    fc.assert(
      fc.property(
        labelArb,
        fc.double({ min: 0.1, max: 200, noNaN: true }),
        (weightLabel, weightKg) => {
          const patient = makePatient({ fullName: 'Test', weightKg });
          const { container } = render(
            <PatientCard patient={patient} labels={{ weight: weightLabel }} />,
          );
          expect(container.textContent).toContain(weightLabel);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('does not render weight label when weightKg is undefined', () => {
    // Feature: ux-improvements, Property 5: PatientCard renders provided labels
    const uniqueLabel = 'XYZWEIGHT_UNIQUE';
    const patient = makePatient({ fullName: 'Test' });
    const { container } = render(
      <PatientCard patient={patient} labels={{ weight: uniqueLabel }} />,
    );
    expect(container.textContent).not.toContain(uniqueLabel);
  });

  it('renders dateOfBirth label only when dateOfBirth is defined', () => {
    // Feature: ux-improvements, Property 5: PatientCard renders provided labels
    fc.assert(
      fc.property(
        labelArb,
        (dobLabel) => {
          const patient = makePatient({ fullName: 'Test', dateOfBirth: '2000-01-01' });
          const { container } = render(
            <PatientCard patient={patient} labels={{ dateOfBirth: dobLabel }} />,
          );
          expect(container.textContent).toContain(dobLabel);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('renders medications label when currentMedications is non-empty', () => {
    // Feature: ux-improvements, Property 5: PatientCard renders provided labels
    fc.assert(
      fc.property(
        labelArb,
        labelArb,
        (medsLabel, activeLabel) => {
          const patient = makePatient({
            fullName: 'Test',
            currentMedications: ['Aspirin'],
          });
          const { container } = render(
            <PatientCard patient={patient} labels={{ medications: medsLabel, active: activeLabel }} />,
          );
          const text = container.textContent ?? '';
          expect(text).toContain(medsLabel);
          expect(text).toContain(activeLabel);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('renders comorbidities label when renalFailure or hepaticFailure is true', () => {
    // Feature: ux-improvements, Property 5: PatientCard renders provided labels
    fc.assert(
      fc.property(
        labelArb,
        (comorbLabel) => {
          const patient = makePatient({ fullName: 'Test', renalFailure: true });
          const { container } = render(
            <PatientCard patient={patient} labels={{ comorbidities: comorbLabel }} />,
          );
          expect(container.textContent).toContain(comorbLabel);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('renders unknownPatient label when fullName is undefined', () => {
    // Feature: ux-improvements, Property 5: PatientCard renders provided labels
    fc.assert(
      fc.property(
        labelArb,
        (unknownLabel) => {
          const patient = makePatient({ fullName: undefined });
          const { container } = render(
            <PatientCard patient={patient} labels={{ unknownPatient: unknownLabel }} />,
          );
          expect(container.textContent).toContain(unknownLabel);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('renders none label when allergies list is empty', () => {
    // Feature: ux-improvements, Property 5: PatientCard renders provided labels
    fc.assert(
      fc.property(
        labelArb,
        (noneLabel) => {
          const patient = makePatient({ fullName: 'Test', allergies: [] });
          const { container } = render(
            <PatientCard patient={patient} labels={{ none: noneLabel }} />,
          );
          expect(container.textContent).toContain(noneLabel);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('renders known label when allergies list is non-empty', () => {
    // Feature: ux-improvements, Property 5: PatientCard renders provided labels
    fc.assert(
      fc.property(
        labelArb,
        (knownLabel) => {
          const patient = makePatient({ fullName: 'Test', allergies: ['Penicillin'] });
          const { container } = render(
            <PatientCard patient={patient} labels={{ known: knownLabel }} />,
          );
          expect(container.textContent).toContain(knownLabel);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('falls back to default English labels when labels prop is omitted', () => {
    // Feature: ux-improvements, Property 5: PatientCard renders provided labels
    const patient = makePatient({
      fullName: 'Jane Doe',
      weightKg: 60,
      dateOfBirth: '1990-05-15',
      allergies: ['Penicillin'],
      renalFailure: true,
      currentMedications: ['Aspirin'],
    });
    const { container } = render(<PatientCard patient={patient} />);
    const text = container.textContent ?? '';

    expect(text).toContain('Weight');
    expect(text).toContain('Date of birth');
    expect(text).toContain('Allergies');
    expect(text).toContain('Comorbidities');
    expect(text).toContain('Medications');
    expect(text).toContain('known');
    expect(text).toContain('active');
  });
});
