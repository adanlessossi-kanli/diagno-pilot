// Feature: ux-improvements, Property 3: Patient search filter correctness
// **Validates: Requirements 4.3**

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import type { PatientProfile } from '@diagno-pilot/types';
import { filterPatientsByName } from '../utils/filterPatients';

const patientProfileArb: fc.Arbitrary<PatientProfile> = fc.record({
  id: fc.option(fc.string(), { nil: undefined }),
  fullName: fc.option(fc.string(), { nil: undefined }),
  dateOfBirth: fc.option(fc.string(), { nil: undefined }),
  weightKg: fc.option(fc.double({ min: 0, max: 200, noNaN: true }), { nil: undefined }),
  ageGroup: fc.option(
    fc.constantFrom('neonatal', 'infant', 'child', 'adult'),
    { nil: undefined },
  ),
  allergies: fc.array(fc.string()),
  renalFailure: fc.boolean(),
  hepaticFailure: fc.boolean(),
  currentMedications: fc.array(fc.string()),
});

describe('P3: Patient search filter correctness', () => {
  it('returns the full input list when query is empty or whitespace-only', () => {
    // Feature: ux-improvements, Property 3: Patient search filter correctness
    fc.assert(
      fc.property(
        fc.array(patientProfileArb),
        fc.array(fc.constantFrom(' ', '\t', '\n', '\r')).map((chars) => chars.join('')),
        (patients, whitespaceQuery) => {
          expect(filterPatientsByName(patients, whitespaceQuery)).toEqual(patients);
          expect(filterPatientsByName(patients, '')).toEqual(patients);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('returns only patients whose fullName contains the query as a case-insensitive substring', () => {
    // Feature: ux-improvements, Property 3: Patient search filter correctness
    fc.assert(
      fc.property(
        fc.array(patientProfileArb),
        fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0),
        (patients, query) => {
          const result = filterPatientsByName(patients, query);
          const lowerQuery = query.trim().toLowerCase();
          for (const p of result) {
            expect(p.fullName).toBeDefined();
            expect(p.fullName!.toLowerCase()).toContain(lowerQuery);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('excludes patients with null/undefined fullName when query is non-empty', () => {
    // Feature: ux-improvements, Property 3: Patient search filter correctness
    fc.assert(
      fc.property(
        fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0),
        (query) => {
          const patients: PatientProfile[] = [
            { fullName: undefined, allergies: [], renalFailure: false, hepaticFailure: false, currentMedications: [] },
            { fullName: 'Alice', allergies: [], renalFailure: false, hepaticFailure: false, currentMedications: [] },
            { allergies: [], renalFailure: false, hepaticFailure: false, currentMedications: [] },
          ];
          const result = filterPatientsByName(patients, query);
          for (const p of result) {
            expect(p.fullName).not.toBeUndefined();
            expect(p.fullName).not.toBeNull();
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('result is always a subset of the original list, preserving order', () => {
    // Feature: ux-improvements, Property 3: Patient search filter correctness
    fc.assert(
      fc.property(
        fc.array(patientProfileArb),
        fc.string(),
        (patients, query) => {
          const result = filterPatientsByName(patients, query);
          // Every result element must be in the original list
          for (const p of result) {
            expect(patients).toContain(p);
          }
          // Result length must not exceed original
          expect(result.length).toBeLessThanOrEqual(patients.length);
          // Order is preserved: indices in original list must be strictly increasing
          const indices = result.map((p) => patients.indexOf(p));
          for (let i = 1; i < indices.length; i++) {
            expect(indices[i]).toBeGreaterThan(indices[i - 1]);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('returns an empty array when the input list is empty, regardless of query', () => {
    // Feature: ux-improvements, Property 3: Patient search filter correctness
    fc.assert(
      fc.property(
        fc.string(),
        (query) => {
          expect(filterPatientsByName([], query)).toEqual([]);
        },
      ),
      { numRuns: 100 },
    );
  });
});
