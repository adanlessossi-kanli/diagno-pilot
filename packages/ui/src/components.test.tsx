import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { AlertBanner } from './AlertBanner';
import { PatientCard } from './PatientCard';
import { SymptomInput } from './SymptomInput';
import { PrescriptionCard } from './PrescriptionCard';
import { SourceCitation } from './SourceCitation';
import type { SafetyAlert, PatientProfile, Symptom, Prescription, DocumentSource } from '@diagno-pilot/types';

// ─── AlertBanner ─────────────────────────────────────────────────────────────

describe('AlertBanner', () => {
  const criticalAlert: SafetyAlert = {
    level: 'critical',
    type: 'allergy',
    message: 'Patient is allergic to penicillin',
    affected_drug: 'Amoxicillin',
  };

  it('renders the alert message', () => {
    render(<AlertBanner alert={criticalAlert} />);
    expect(screen.getByText('Patient is allergic to penicillin')).toBeTruthy();
  });

  it('shows the affected drug', () => {
    render(<AlertBanner alert={criticalAlert} />);
    expect(screen.getByText('Amoxicillin')).toBeTruthy();
  });

  it('calls onDismiss when dismiss button is clicked', () => {
    const onDismiss = vi.fn();
    render(<AlertBanner alert={criticalAlert} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByLabelText('Dismiss alert'));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it('does not render dismiss button when onDismiss is not provided', () => {
    render(<AlertBanner alert={criticalAlert} />);
    expect(screen.queryByLabelText('Dismiss alert')).toBeNull();
  });

  it('renders warning level alert', () => {
    const warning: SafetyAlert = { level: 'warning', type: 'interaction', message: 'Drug interaction detected' };
    render(<AlertBanner alert={warning} />);
    expect(screen.getByText('Drug interaction detected')).toBeTruthy();
  });

  it('renders info level alert', () => {
    const info: SafetyAlert = { level: 'info', type: 'contraindication', message: 'Dose adjusted for renal failure' };
    render(<AlertBanner alert={info} />);
    expect(screen.getByText('Dose adjusted for renal failure')).toBeTruthy();
  });
});

// ─── PatientCard ─────────────────────────────────────────────────────────────

describe('PatientCard', () => {
  const patient: PatientProfile = {
    fullName: 'Jean Dupont',
    dateOfBirth: '2010-05-15',
    weightKg: 32,
    ageGroup: 'child',
    allergies: ['penicillin', 'sulfonamides'],
    renalFailure: false,
    hepaticFailure: true,
    currentMedications: ['paracetamol'],
  };

  it('renders patient name', () => {
    render(<PatientCard patient={patient} />);
    expect(screen.getByText('Jean Dupont')).toBeTruthy();
  });

  it('renders weight', () => {
    render(<PatientCard patient={patient} />);
    expect(screen.getByText('32 kg')).toBeTruthy();
  });

  it('renders allergies count', () => {
    render(<PatientCard patient={patient} />);
    expect(screen.getByText('2 known')).toBeTruthy();
  });

  it('shows hepatic failure comorbidity', () => {
    render(<PatientCard patient={patient} />);
    expect(screen.getByText('Hepatic failure')).toBeTruthy();
  });

  it('shows "None" when no allergies', () => {
    render(<PatientCard patient={{ ...patient, allergies: [] }} />);
    expect(screen.getByText('None')).toBeTruthy();
  });

  it('shows "Unknown patient" when fullName is absent', () => {
    render(<PatientCard patient={{ ...patient, fullName: undefined }} />);
    expect(screen.getByText('Unknown patient')).toBeTruthy();
  });
});

// ─── SymptomInput ─────────────────────────────────────────────────────────────

describe('SymptomInput', () => {
  const symptoms: Symptom[] = [
    { name: 'Fever', severity: 'severe', duration_days: 3 },
  ];

  it('renders existing symptoms', () => {
    render(<SymptomInput symptoms={symptoms} onAdd={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByText('Fever')).toBeTruthy();
  });

  it('calls onAdd with new symptom when Add is clicked', () => {
    const onAdd = vi.fn();
    render(<SymptomInput symptoms={[]} onAdd={onAdd} onRemove={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Symptom name'), { target: { value: 'Cough' } });
    fireEvent.click(screen.getByText('Add'));
    expect(onAdd).toHaveBeenCalledWith(expect.objectContaining({ name: 'Cough' }));
  });

  it('calls onRemove when remove button is clicked', () => {
    const onRemove = vi.fn();
    render(<SymptomInput symptoms={symptoms} onAdd={vi.fn()} onRemove={onRemove} />);
    fireEvent.click(screen.getByLabelText('Remove Fever'));
    expect(onRemove).toHaveBeenCalledWith(0);
  });

  it('does not call onAdd when symptom name is empty', () => {
    const onAdd = vi.fn();
    render(<SymptomInput symptoms={[]} onAdd={onAdd} onRemove={vi.fn()} />);
    fireEvent.click(screen.getByText('Add'));
    expect(onAdd).not.toHaveBeenCalled();
  });
});

// ─── PrescriptionCard ─────────────────────────────────────────────────────────

describe('PrescriptionCard', () => {
  const rx: Prescription = {
    antibiotic: 'Amoxicillin',
    dose_mg: 500,
    dose_per_kg: 25,
    frequency: 'TID',
    duration_days: 7,
    route: 'oral',
    is_capped_to_adult_dose: false,
  };

  it('renders antibiotic name', () => {
    render(<PrescriptionCard prescription={rx} />);
    expect(screen.getByText('Amoxicillin')).toBeTruthy();
  });

  it('renders dose and frequency', () => {
    render(<PrescriptionCard prescription={rx} />);
    expect(screen.getByText(/500 mg/)).toBeTruthy();
    expect(screen.getByText('TID')).toBeTruthy();
  });

  it('shows capped badge when is_capped_to_adult_dose is true', () => {
    render(<PrescriptionCard prescription={{ ...rx, is_capped_to_adult_dose: true }} />);
    expect(screen.getByText(/Capped to adult dose/)).toBeTruthy();
  });

  it('does not show capped badge when not capped', () => {
    render(<PrescriptionCard prescription={rx} />);
    expect(screen.queryByText(/Capped to adult dose/)).toBeNull();
  });
});

// ─── SourceCitation ───────────────────────────────────────────────────────────

describe('SourceCitation', () => {
  const source: DocumentSource = {
    title: 'OMS AFRO Guidelines',
    section: 'Chapter 3 — Antibiotics',
    excerpt: 'Amoxicillin is the first-line treatment for community-acquired pneumonia.',
  };

  it('renders document title and section', () => {
    render(<SourceCitation source={source} />);
    expect(screen.getByText('OMS AFRO Guidelines')).toBeTruthy();
    expect(screen.getByText(/Chapter 3/)).toBeTruthy();
  });

  it('renders excerpt when provided', () => {
    render(<SourceCitation source={source} />);
    expect(screen.getByText(/Amoxicillin is the first-line/)).toBeTruthy();
  });

  it('renders without excerpt when not provided', () => {
    const noExcerpt: DocumentSource = { title: 'MSF Guide', section: 'Malaria', excerpt: '' };
    render(<SourceCitation source={noExcerpt} />);
    expect(screen.getByText('MSF Guide')).toBeTruthy();
  });
});
