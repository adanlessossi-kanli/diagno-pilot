/**
 * Unit tests for MobilePatientCard (REQ 10.2, 12.1, 12.2)
 *
 * Covers:
 *  a. Renders the patient's full name
 *  b. Renders the date of birth when provided
 *  c. Renders the correct age group label for each AgeGroup value
 *  d. Falls back to "Patient inconnu" when fullName is absent
 *  e. Does not render age group section when ageGroup is absent
 *  f. Renders weight when provided
 *  g. Renders allergy count when allergies are present
 *  h. Renders comorbidities when renal/hepatic failure flags are set
 *  i. Renders current medications count when present
 *  j. Renders initials avatar (not emoji) — REQ 12.2
 *  k. Avatar uses primary[600] token background color — REQ 12.2
 */
import React from 'react';
import { render, screen } from '@testing-library/react-native';
import { MobilePatientCard } from '../MobilePatientCard';
import { colors } from '@diagno-pilot/ui/src/tokens';
import type { PatientProfile } from '@diagno-pilot/types';

const basePatient: PatientProfile = {
  id: 'p1',
  fullName: 'Kofi Mensah',
  ageGroup: 'adult',
  allergies: [],
  currentMedications: [],
  renalFailure: false,
  hepaticFailure: false,
};

describe('MobilePatientCard', () => {
  it('a. renders the patient full name', () => {
    render(<MobilePatientCard patient={basePatient} />);
    expect(screen.getByText('Kofi Mensah')).toBeTruthy();
  });

  it('b. renders the date of birth when provided', () => {
    render(<MobilePatientCard patient={{ ...basePatient, dateOfBirth: '1990-05-12' }} />);
    expect(screen.getByText('1990-05-12')).toBeTruthy();
  });

  it('c. renders correct age group label — adult', () => {
    render(<MobilePatientCard patient={{ ...basePatient, ageGroup: 'adult' }} />);
    expect(screen.getByText('Adulte (18+)')).toBeTruthy();
  });

  it('c. renders correct age group label — child', () => {
    render(<MobilePatientCard patient={{ ...basePatient, ageGroup: 'child' }} />);
    expect(screen.getByText('Enfant (2–17 ans)')).toBeTruthy();
  });

  it('c. renders correct age group label — infant', () => {
    render(<MobilePatientCard patient={{ ...basePatient, ageGroup: 'infant' }} />);
    expect(screen.getByText('Nourrisson (1–23 mois)')).toBeTruthy();
  });

  it('c. renders correct age group label — neonatal', () => {
    render(<MobilePatientCard patient={{ ...basePatient, ageGroup: 'neonatal' }} />);
    expect(screen.getByText('Néonatal (0–28j)')).toBeTruthy();
  });

  it('d. falls back to "Patient inconnu" when fullName is absent', () => {
    render(<MobilePatientCard patient={{ ...basePatient, fullName: undefined }} />);
    expect(screen.getByText('Patient inconnu')).toBeTruthy();
  });

  it('e. does not render age group when ageGroup is absent', () => {
    render(<MobilePatientCard patient={{ ...basePatient, ageGroup: undefined }} />);
    expect(screen.queryByText(/Adulte|Enfant|Nourrisson|Néonatal/)).toBeNull();
  });

  it('f. renders weight when provided', () => {
    render(<MobilePatientCard patient={{ ...basePatient, weightKg: 72 }} />);
    expect(screen.getByText('72 kg')).toBeTruthy();
  });

  it('g. renders allergy count when allergies are present', () => {
    render(
      <MobilePatientCard
        patient={{ ...basePatient, allergies: ['pénicilline', 'amoxicilline'] }}
      />
    );
    expect(screen.getByText('2 connue(s)')).toBeTruthy();
  });

  it('g. renders "Aucune" when no allergies', () => {
    render(<MobilePatientCard patient={{ ...basePatient, allergies: [] }} />);
    expect(screen.getByText('Aucune')).toBeTruthy();
  });

  it('h. renders renal failure comorbidity', () => {
    render(<MobilePatientCard patient={{ ...basePatient, renalFailure: true }} />);
    expect(screen.getByText(/Insuff\. rénale/)).toBeTruthy();
  });

  it('h. renders hepatic failure comorbidity', () => {
    render(<MobilePatientCard patient={{ ...basePatient, hepaticFailure: true }} />);
    expect(screen.getByText(/Insuff\. hépatique/)).toBeTruthy();
  });

  it('i. renders current medications count when present', () => {
    render(
      <MobilePatientCard
        patient={{ ...basePatient, currentMedications: ['metformine', 'amlodipine'] }}
      />
    );
    expect(screen.getByText('2 en cours')).toBeTruthy();
  });

  it('j. renders initials avatar instead of emoji — REQ 12.2', () => {
    render(<MobilePatientCard patient={{ ...basePatient, fullName: 'Kofi Mensah' }} />);
    // Initials "KM" should be rendered as text
    expect(screen.getByText('KM')).toBeTruthy();
    // No emoji avatar text should be present
    expect(screen.queryByText('👤')).toBeNull();
  });

  it('j. derives single initial when only one name part', () => {
    render(<MobilePatientCard patient={{ ...basePatient, fullName: 'Amara' }} />);
    expect(screen.getByText('A')).toBeTruthy();
  });

  it('j. renders "?" initials when fullName is absent', () => {
    render(<MobilePatientCard patient={{ ...basePatient, fullName: undefined }} />);
    expect(screen.getByText('?')).toBeTruthy();
  });

  it('k. avatar container uses primary[600] token as background color — REQ 12.2', () => {
    render(<MobilePatientCard patient={basePatient} />);
    const avatar = screen.getByLabelText('Avatar de Kofi Mensah');
    const style = avatar.props.style;
    const flatStyle: Record<string, unknown> = {};
    (Array.isArray(style) ? style : [style]).forEach((s: unknown) => {
      if (s && typeof s === 'object') Object.assign(flatStyle, s);
    });
    expect(flatStyle.backgroundColor).toBe(colors.primary[600]);
  });
});
