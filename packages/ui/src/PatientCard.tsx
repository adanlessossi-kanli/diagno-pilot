import React from 'react';
import type { PatientProfile } from '@diagno-pilot/types';

// REQ-06: Patient profile display

export interface PatientCardProps {
  patient: PatientProfile;
}

const ageGroupLabel: Record<string, string> = {
  neonatal: 'Neonatal (0–28d)',
  infant: 'Infant (1–23mo)',
  child: 'Child (2–17y)',
  adult: 'Adult (18+)',
};

function getInitials(fullName: string): string {
  return fullName
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((n) => n[0]?.toUpperCase() ?? '')
    .join('');
}

export function PatientCard({ patient }: PatientCardProps) {
  const initials = getInitials(patient.fullName ?? '');

  return (
    <div className="border border-neutral-200 rounded-lg p-4 bg-white max-w-sm shadow-sm">
      <div className="flex items-center gap-3 mb-3">
        <div
          aria-hidden="true"
          className="w-10 h-10 rounded-full bg-primary-600 flex items-center justify-center text-white text-sm font-semibold shrink-0"
        >
          {initials || '?'}
        </div>
        <div>
          <h3 className="m-0 text-base font-semibold text-neutral-900">
            {patient.fullName ?? 'Unknown patient'}
          </h3>
          {patient.ageGroup && (
            <span className="text-xs text-neutral-500">
              {ageGroupLabel[patient.ageGroup] ?? patient.ageGroup}
            </span>
          )}
        </div>
      </div>

      <dl className="m-0 grid grid-cols-2 gap-2">
        {patient.weightKg !== undefined && (
          <>
            <dt className="m-0 text-xs text-neutral-500 font-medium">Weight</dt>
            <dd className="m-0 text-sm text-neutral-900">{patient.weightKg} kg</dd>
          </>
        )}
        {patient.dateOfBirth && (
          <>
            <dt className="m-0 text-xs text-neutral-500 font-medium">Date of birth</dt>
            <dd className="m-0 text-sm text-neutral-900">{patient.dateOfBirth}</dd>
          </>
        )}
        <dt className="m-0 text-xs text-neutral-500 font-medium">Allergies</dt>
        <dd className="m-0 text-sm text-neutral-900">
          {patient.allergies.length > 0
            ? `${patient.allergies.length} known`
            : 'None'}
        </dd>
        {(patient.renalFailure || patient.hepaticFailure) && (
          <>
            <dt className="m-0 text-xs text-neutral-500 font-medium">Comorbidities</dt>
            <dd className="m-0 text-sm text-neutral-900">
              {[
                patient.renalFailure && 'Renal failure',
                patient.hepaticFailure && 'Hepatic failure',
              ]
                .filter(Boolean)
                .join(', ')}
            </dd>
          </>
        )}
        {patient.currentMedications.length > 0 && (
          <>
            <dt className="m-0 text-xs text-neutral-500 font-medium">Medications</dt>
            <dd className="m-0 text-sm text-neutral-900">{patient.currentMedications.length} active</dd>
          </>
        )}
      </dl>
    </div>
  );
}
