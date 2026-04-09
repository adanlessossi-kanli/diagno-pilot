import React from 'react';
import type { Prescription } from '@diagno-pilot/types';

// REQ-03: Prescription display with dose capping indicator

export interface PrescriptionCardProps {
  prescription: Prescription;
}

export function PrescriptionCard({ prescription: rx }: PrescriptionCardProps) {
  return (
    <div className="border border-neutral-200 rounded-lg p-4 bg-white max-w-sm shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <h3 className="m-0 text-base font-bold text-neutral-900">
          {rx.antibiotic}
        </h3>
        {rx.isCappedToAdultDose && (
          <span
            title="Dose capped to maximum adult dose"
            className="bg-warning-bg text-warning-text border border-warning-border rounded-full px-2.5 py-0.5 text-xs font-semibold tracking-wide"
          >
            ⚠ Capped to adult dose
          </span>
        )}
      </div>

      <dl className="m-0 grid grid-cols-2 gap-2">
        <dt className="m-0 text-xs text-neutral-500 font-medium">Dose</dt>
        <dd className="m-0 text-sm text-neutral-900">
          {rx.doseMg} mg
          {rx.dosePerKg !== undefined && (
            <span className="text-neutral-500 ml-1">({rx.dosePerKg} mg/kg)</span>
          )}
        </dd>

        <dt className="m-0 text-xs text-neutral-500 font-medium">Frequency</dt>
        <dd className="m-0 text-sm text-neutral-900">{rx.frequency}</dd>

        <dt className="m-0 text-xs text-neutral-500 font-medium">Duration</dt>
        <dd className="m-0 text-sm text-neutral-900">
          {rx.durationDays} day{rx.durationDays !== 1 ? 's' : ''}
        </dd>

        <dt className="m-0 text-xs text-neutral-500 font-medium">Route</dt>
        <dd className="m-0 text-sm text-neutral-900">{rx.route}</dd>
      </dl>
    </div>
  );
}
