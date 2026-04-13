import type { PatientProfile } from '@diagno-pilot/types';

/**
 * Case-insensitive substring match on patient.fullName.
 * Returns full list when query is empty/whitespace.
 * Excludes patients with null/undefined fullName when query is non-empty.
 * Preserves original order.
 */
export function filterPatientsByName(
  patients: PatientProfile[],
  query: string
): PatientProfile[] {
  const trimmed = query.trim();
  if (trimmed === '') return patients;
  const lowerQuery = trimmed.toLowerCase();
  return patients.filter(
    (p) => p.fullName != null && p.fullName.toLowerCase().includes(lowerQuery)
  );
}
