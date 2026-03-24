import React from 'react';
import type { Prescription } from '@diagno-pilot/types';

// REQ-03: Prescription display with dose capping indicator

export interface PrescriptionCardProps {
  prescription: Prescription;
}

export function PrescriptionCard({ prescription: rx }: PrescriptionCardProps) {
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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#111827' }}>
          {rx.antibiotic}
        </h3>
        {rx.is_capped_to_adult_dose && (
          <span
            title="Dose capped to maximum adult dose"
            style={{
              backgroundColor: '#fef3c7',
              color: '#92400e',
              border: '1px solid #fcd34d',
              borderRadius: '12px',
              padding: '2px 10px',
              fontSize: '11px',
              fontWeight: 600,
              letterSpacing: '0.03em',
            }}
          >
            ⚠ Capped to adult dose
          </span>
        )}
      </div>

      <dl style={{ margin: 0, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
        <dt style={dtStyle}>Dose</dt>
        <dd style={ddStyle}>
          {rx.dose_mg} mg
          {rx.dose_per_kg !== undefined && (
            <span style={{ color: '#6b7280', marginLeft: '4px' }}>({rx.dose_per_kg} mg/kg)</span>
          )}
        </dd>

        <dt style={dtStyle}>Frequency</dt>
        <dd style={ddStyle}>{rx.frequency}</dd>

        <dt style={dtStyle}>Duration</dt>
        <dd style={ddStyle}>{rx.duration_days} day{rx.duration_days !== 1 ? 's' : ''}</dd>

        <dt style={dtStyle}>Route</dt>
        <dd style={ddStyle}>{rx.route}</dd>
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
