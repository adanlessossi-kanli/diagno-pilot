import React from 'react';
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import * as fc from 'fast-check';
import { PatientCard } from '../PatientCard';
import type { PatientProfile } from '@diagno-pilot/types';

// Feature: ui-professional-refactor, Property 9: Card surface styling invariant
// For any generated patient record, the rendered card has white background class,
// rounded-lg/rounded-md, and a shadow class.

function makePatient(overrides: Partial<PatientProfile> = {}): PatientProfile {
  return {
    allergies: [],
    renalFailure: false,
    hepaticFailure: false,
    currentMedications: [],
    ...overrides,
  };
}

describe('P9: Card surface styling invariant', () => {
  it('card always has white bg, rounded corners, and shadow for any patient record', () => {
    // Feature: ui-professional-refactor, Property 9: Card surface styling invariant
    fc.assert(
      fc.property(
        fc.record({
          fullName: fc.string({ minLength: 1 }),
          allergies: fc.array(fc.string()),
        }),
        ({ fullName, allergies }) => {
          const patient = makePatient({ fullName, allergies });
          const { container } = render(<PatientCard patient={patient} />);
          const card = container.firstElementChild as HTMLElement;
          const classes = card.className;

          // White background
          expect(classes).toContain('bg-white');
          // Rounded corners (rounded-lg or rounded-md)
          expect(classes.match(/rounded-(lg|md|xl)/)).not.toBeNull();
          // Shadow class
          expect(classes.match(/shadow(-\w+)?/)).not.toBeNull();
        },
      ),
      { numRuns: 100 },
    );
  });

  it('renders initials avatar instead of emoji', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1 }),
        (fullName) => {
          const patient = makePatient({ fullName });
          const { container } = render(<PatientCard patient={patient} />);
          // No emoji in rendered output
          const emojiRegex = /[\u{1F300}-\u{1FFFF}]/u;
          expect(emojiRegex.test(container.textContent ?? '')).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('initials avatar uses primary-600 background class', () => {
    const patient = makePatient({ fullName: 'Jane Doe' });
    const { container } = render(<PatientCard patient={patient} />);
    const avatar = container.querySelector('[aria-hidden="true"]') as HTMLElement;
    expect(avatar.className).toContain('bg-primary-600');
    expect(avatar.textContent).toBe('JD');
  });

  it('renders unknown patient gracefully', () => {
    const patient = makePatient({ fullName: undefined });
    const { getByText } = render(<PatientCard patient={patient} />);
    expect(getByText('Unknown patient')).toBeTruthy();
  });
});
