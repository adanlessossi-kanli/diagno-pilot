import React from 'react';
import type { PatientProfile } from '@diagno-pilot/types';

// REQ-06: Patient profile display

export interface PatientCardLabels {
  weight?: string;
  dateOfBirth?: string;
  allergies?: string;
  comorbidities?: string;
  medications?: string;
  unknownPatient?: string;
  none?: string;
  known?: string;
  active?: string;
}

const defaultLabels: Required<PatientCardLabels> = {
  weight: 'Weight',
  dateOfBirth: 'Date of birth',
  allergies: 'Allergies',
  comorbidities: 'Comorbidities',
  medications: 'Medications',
  unknownPatient: 'Unknown patient',
  none: 'None',
  known: 'known',
  active: 'active',
};

export interface PatientCardProps {
  patient: PatientProfile;
  labels?: PatientCardLabels;
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

export function PatientCard({ patient, labels: labelsProp }: PatientCardProps) {
  const labels = { ...defaultLabels, ...labelsProp };
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
            {patient.fullName ?? labels.unknownPatient}
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
            <dt className="m-0 text-xs text-neutral-500 font-medium">{labels.weight}</dt>
            <dd className="m-0 text-sm text-neutral-900">{patient.weightKg} kg</dd>
          </>
        )}
        {patient.dateOfBirth && (
          <>
            <dt className="m-0 text-xs text-neutral-500 font-medium">{labels.dateOfBirth}</dt>
            <dd className="m-0 text-sm text-neutral-900">{patient.dateOfBirth}</dd>
          </>
        )}
        <dt className="m-0 text-xs text-neutral-500 font-medium">{labels.allergies}</dt>
        <dd className="m-0 text-sm text-neutral-900">
          {patient.allergies.length > 0
            ? `${patient.allergies.length} ${labels.known}`
            : labels.none}
        </dd>
        {(patient.renalFailure || patient.hepaticFailure) && (
          <>
            <dt className="m-0 text-xs text-neutral-500 font-medium">{labels.comorbidities}</dt>
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
            <dt className="m-0 text-xs text-neutral-500 font-medium">{labels.medications}</dt>
            <dd className="m-0 text-sm text-neutral-900">{patient.currentMedications.length} {labels.active}</dd>
          </>
        )}
      </dl>
    </div>
  );
}
