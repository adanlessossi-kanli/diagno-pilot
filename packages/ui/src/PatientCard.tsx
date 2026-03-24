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

export function PatientCard({ patient }: PatientCardProps) {
  return (
    <div
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: '8px',
        padding: '16px',
        backgroundColor: '#fff',
        maxWidth: '400px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
        <div
          aria-hidden="true"
          style={{
            width: '40px',
            height: '40px',
            borderRadius: '50%',
            backgroundColor: '#dbeafe',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '20px',
          }}
        >
          👤
        </div>
        <div>
          <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: '#111827' }}>
            {patient.fullName ?? 'Unknown patient'}
          </h3>
          {patient.ageGroup && (
            <span style={{ fontSize: '12px', color: '#6b7280' }}>
              {ageGroupLabel[patient.ageGroup] ?? patient.ageGroup}
            </span>
          )}
        </div>
      </div>

      <dl style={{ margin: 0, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
        {patient.weightKg !== undefined && (
          <>
            <dt style={dtStyle}>Weight</dt>
            <dd style={ddStyle}>{patient.weightKg} kg</dd>
          </>
        )}
        {patient.dateOfBirth && (
          <>
            <dt style={dtStyle}>Date of birth</dt>
            <dd style={ddStyle}>{patient.dateOfBirth}</dd>
          </>
        )}
        <dt style={dtStyle}>Allergies</dt>
        <dd style={ddStyle}>
          {patient.allergies.length > 0
            ? `${patient.allergies.length} known`
            : 'None'}
        </dd>
        {(patient.renalFailure || patient.hepaticFailure) && (
          <>
            <dt style={dtStyle}>Comorbidities</dt>
            <dd style={ddStyle}>
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
            <dt style={dtStyle}>Medications</dt>
            <dd style={ddStyle}>{patient.currentMedications.length} active</dd>
          </>
        )}
      </dl>
    </div>
  );
}

const dtStyle: React.CSSProperties = {
  margin: 0,
  fontSize: '12px',
  color: '#6b7280',
  fontWeight: 500,
};

const ddStyle: React.CSSProperties = {
  margin: 0,
  fontSize: '13px',
  color: '#111827',
};
