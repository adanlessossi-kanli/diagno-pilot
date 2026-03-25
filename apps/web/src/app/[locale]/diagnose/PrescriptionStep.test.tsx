/**
 * Unit tests for PrescriptionStep component
 * Validates: Requirements REQ-09 (safety alerts, critical blocking, therapeutic alternatives)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { PrescriptionStep } from './PrescriptionStep';
import type { PrescriptionResponse } from '@diagno-pilot/api-client';
import type { DifferentialDiagnosis } from '@diagno-pilot/types';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) => {
    if (params && 'days' in params) return `${params.days} days`;
    return key;
  },
}));

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const mockDiagnoses: DifferentialDiagnosis[] = [
  {
    condition: 'Pneumonia',
    probability: 0.85,
    icd_code: 'J18.9',
    concordant_symptoms: ['fever', 'cough'],
  },
];

const basePrescription = {
  antibiotic: 'Amoxicillin',
  dose_mg: 500,
  frequency: 'every 8 hours',
  duration_days: 7,
  route: 'oral' as const,
  is_capped_to_adult_dose: false,
};

function makeResponse(overrides: Partial<PrescriptionResponse> = {}): PrescriptionResponse {
  return {
    prescription: basePrescription,
    alerts: [],
    llmUsed: 'test-llm',
    sources: [],
    ...overrides,
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function renderComponent(onGetPrescription: () => Promise<PrescriptionResponse>) {
  return render(
    <PrescriptionStep
      diagnoses={mockDiagnoses}
      onGetPrescription={onGetPrescription}
    />,
  );
}

function clickGetPrescription() {
  const btn = screen.getByRole('button', { name: /getPrescription/i });
  act(() => { fireEvent.click(btn); });
}

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PrescriptionStep', () => {
  it('1. renders prescription details after clicking get prescription', async () => {
    const onGetPrescription = vi.fn().mockResolvedValue(makeResponse());
    renderComponent(onGetPrescription);

    await clickGetPrescription();

    await waitFor(() => {
      expect(screen.getByText('Amoxicillin')).toBeInTheDocument();
    });

    expect(screen.getByText('500 mg')).toBeInTheDocument();
    expect(screen.getByText('every 8 hours')).toBeInTheDocument();
    expect(screen.getByText('7 days')).toBeInTheDocument();
    expect(screen.getByText('oral')).toBeInTheDocument();
  });

  it('2. shows pediatric dose per kg when dose_per_kg is set', async () => {
    const onGetPrescription = vi.fn().mockResolvedValue(
      makeResponse({
        prescription: { ...basePrescription, dose_per_kg: 25 },
      }),
    );
    renderComponent(onGetPrescription);

    await clickGetPrescription();

    await waitFor(() => {
      expect(screen.getByText(/25 mg\/kg/)).toBeInTheDocument();
    });
  });

  it('3. shows adult dose cap badge when is_capped_to_adult_dose is true', async () => {
    const onGetPrescription = vi.fn().mockResolvedValue(
      makeResponse({
        prescription: { ...basePrescription, is_capped_to_adult_dose: true },
      }),
    );
    renderComponent(onGetPrescription);

    await clickGetPrescription();

    await waitFor(() => {
      expect(screen.getByText(/cappedToAdultDose/)).toBeInTheDocument();
    });
  });

  it('4. critical alert blocks workflow — shows critical alert section with message', async () => {
    const onGetPrescription = vi.fn().mockResolvedValue(
      makeResponse({
        alerts: [
          {
            level: 'critical',
            type: 'allergy',
            message: 'Patient is allergic to penicillin',
          },
        ],
      }),
    );
    renderComponent(onGetPrescription);

    await clickGetPrescription();

    await waitFor(() => {
      expect(screen.getByText('criticalAlertTitle')).toBeInTheDocument();
    });

    expect(screen.getByText('Patient is allergic to penicillin')).toBeInTheDocument();
  });

  it('5. critical alert — confirmation checkbox is present and unchecked by default', async () => {
    const onGetPrescription = vi.fn().mockResolvedValue(
      makeResponse({
        alerts: [
          {
            level: 'critical',
            type: 'allergy',
            message: 'Critical allergy detected',
          },
        ],
      }),
    );
    renderComponent(onGetPrescription);

    await clickGetPrescription();

    await waitFor(() => {
      const checkbox = screen.getByRole('checkbox');
      expect(checkbox).toBeInTheDocument();
      expect(checkbox).not.toBeChecked();
    });
  });

  it('6. confirmation checkbox can be checked to acknowledge critical alert', async () => {
    const onGetPrescription = vi.fn().mockResolvedValue(
      makeResponse({
        alerts: [
          {
            level: 'critical',
            type: 'allergy',
            message: 'Critical allergy detected',
          },
        ],
      }),
    );
    renderComponent(onGetPrescription);

    await clickGetPrescription();

    await waitFor(() => {
      expect(screen.getByRole('checkbox')).toBeInTheDocument();
    });

    const checkbox = screen.getByRole('checkbox');
    act(() => { fireEvent.click(checkbox); });

    expect(checkbox).toBeChecked();
  });

  it('7. therapeutic alternative is shown for critical alert with alternative field', async () => {
    const onGetPrescription = vi.fn().mockResolvedValue(
      makeResponse({
        alerts: [
          {
            level: 'critical',
            type: 'allergy',
            message: 'Allergy to penicillin',
            alternative: 'Consider Azithromycin 500mg',
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          } as any,
        ],
      }),
    );
    renderComponent(onGetPrescription);

    await clickGetPrescription();

    await waitFor(() => {
      expect(screen.getByText('Consider Azithromycin 500mg')).toBeInTheDocument();
    });

    expect(screen.getByText('alternativeTitle')).toBeInTheDocument();
  });

  it('8. warning alert is shown without a confirmation checkbox', async () => {
    const onGetPrescription = vi.fn().mockResolvedValue(
      makeResponse({
        alerts: [
          {
            level: 'warning',
            type: 'interaction',
            message: 'Moderate drug interaction detected',
          },
        ],
      }),
    );
    renderComponent(onGetPrescription);

    await clickGetPrescription();

    await waitFor(() => {
      expect(screen.getByText('Moderate drug interaction detected')).toBeInTheDocument();
    });

    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('9. info alert is shown', async () => {
    const onGetPrescription = vi.fn().mockResolvedValue(
      makeResponse({
        alerts: [
          {
            level: 'info',
            type: 'contraindication',
            message: 'Take with food',
          },
        ],
      }),
    );
    renderComponent(onGetPrescription);

    await clickGetPrescription();

    await waitFor(() => {
      expect(screen.getByText('Take with food')).toBeInTheDocument();
    });
  });

  it('10. no alerts shows success message', async () => {
    const onGetPrescription = vi.fn().mockResolvedValue(makeResponse({ alerts: [] }));
    renderComponent(onGetPrescription);

    await clickGetPrescription();

    await waitFor(() => {
      expect(screen.getByText(/noAlerts/)).toBeInTheDocument();
    });
  });

  it('11. error state — shows error message when onGetPrescription rejects', async () => {
    const onGetPrescription = vi.fn().mockRejectedValue(new Error('Network error'));
    renderComponent(onGetPrescription);

    await clickGetPrescription();

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    expect(screen.getByText('errorPrescription')).toBeInTheDocument();
  });
});
