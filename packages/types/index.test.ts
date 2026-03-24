// Unit tests for shared TypeScript types — REQ-02, REQ-06
import { describe, it, expect } from 'vitest';
import type {
  AgeGroup,
  AlertLevel,
  PatientProfile,
  Prescription,
  SafetyAlert,
  DifferentialDiagnosis,
  Symptom,
  ChatMessage,
  Consultation,
  ChatSession,
  DocumentSource,
} from './index';

// ─── AgeGroup ─────────────────────────────────────────────────────────────────

describe('AgeGroup', () => {
  it('accepts all valid string literals', () => {
    const values: AgeGroup[] = ['neonatal', 'infant', 'child', 'adult'];
    expect(values).toHaveLength(4);
    expect(values).toContain('neonatal');
    expect(values).toContain('infant');
    expect(values).toContain('child');
    expect(values).toContain('adult');
  });
});

// ─── AlertLevel ───────────────────────────────────────────────────────────────

describe('AlertLevel', () => {
  it('accepts all valid string literals', () => {
    const values: AlertLevel[] = ['critical', 'warning', 'info'];
    expect(values).toHaveLength(3);
    expect(values).toContain('critical');
    expect(values).toContain('warning');
    expect(values).toContain('info');
  });
});

// ─── Prescription.route ───────────────────────────────────────────────────────

describe('Prescription', () => {
  it('accepts oral route', () => {
    const p: Prescription = {
      antibiotic: 'Amoxicillin',
      dose_mg: 500,
      frequency: 'TID',
      duration_days: 7,
      route: 'oral',
      is_capped_to_adult_dose: false,
    };
    expect(p.route).toBe('oral');
  });

  it('accepts IV route', () => {
    const p: Prescription = {
      antibiotic: 'Ceftriaxone',
      dose_mg: 1000,
      frequency: 'OD',
      duration_days: 5,
      route: 'IV',
      is_capped_to_adult_dose: false,
    };
    expect(p.route).toBe('IV');
  });

  it('accepts IM route', () => {
    const p: Prescription = {
      antibiotic: 'Benzylpenicillin',
      dose_mg: 600,
      frequency: 'QID',
      duration_days: 10,
      route: 'IM',
      is_capped_to_adult_dose: false,
    };
    expect(p.route).toBe('IM');
  });

  it('serializes and deserializes without data loss', () => {
    const p: Prescription = {
      antibiotic: 'Amoxicillin',
      dose_mg: 250,
      dose_per_kg: 25,
      frequency: 'BID',
      duration_days: 5,
      route: 'oral',
      is_capped_to_adult_dose: true,
    };
    const json = JSON.stringify(p);
    const restored: Prescription = JSON.parse(json);
    expect(restored).toEqual(p);
  });
});

// ─── PatientProfile ───────────────────────────────────────────────────────────

describe('PatientProfile', () => {
  it('constructs a minimal profile with required fields', () => {
    const profile: PatientProfile = {
      allergies: [],
      renalFailure: false,
      hepaticFailure: false,
      currentMedications: [],
    };
    expect(profile.allergies).toEqual([]);
    expect(profile.renalFailure).toBe(false);
    expect(profile.hepaticFailure).toBe(false);
  });

  it('constructs a full profile with all optional fields', () => {
    const profile: PatientProfile = {
      id: 'p-001',
      fullName: 'Jean Dupont',
      dateOfBirth: '1990-05-15',
      weightKg: 70,
      ageGroup: 'adult',
      allergies: ['penicillin'],
      renalFailure: false,
      hepaticFailure: false,
      currentMedications: ['metformin'],
    };
    expect(profile.id).toBe('p-001');
    expect(profile.ageGroup).toBe('adult');
    expect(profile.allergies).toContain('penicillin');
  });

  it('serializes and deserializes without data loss', () => {
    const profile: PatientProfile = {
      id: 'p-002',
      fullName: 'Ama Koffi',
      dateOfBirth: '2020-01-10',
      weightKg: 12,
      ageGroup: 'child',
      allergies: ['sulfonamides'],
      renalFailure: true,
      hepaticFailure: false,
      currentMedications: [],
    };
    const json = JSON.stringify(profile);
    const restored: PatientProfile = JSON.parse(json);
    expect(restored).toEqual(profile);
  });
});

// ─── SafetyAlert ──────────────────────────────────────────────────────────────

describe('SafetyAlert', () => {
  it('constructs a critical allergy alert', () => {
    const alert: SafetyAlert = {
      level: 'critical',
      type: 'allergy',
      message: 'Patient is allergic to penicillin',
      affected_drug: 'Amoxicillin',
    };
    expect(alert.level).toBe('critical');
    expect(alert.type).toBe('allergy');
  });

  it('serializes and deserializes without data loss', () => {
    const alert: SafetyAlert = {
      level: 'warning',
      type: 'interaction',
      message: 'Potential interaction with warfarin',
    };
    const json = JSON.stringify(alert);
    const restored: SafetyAlert = JSON.parse(json);
    expect(restored).toEqual(alert);
  });
});

// ─── DifferentialDiagnosis ────────────────────────────────────────────────────

describe('DifferentialDiagnosis', () => {
  it('constructs a diagnosis entry with optional icd_code', () => {
    const diag: DifferentialDiagnosis = {
      condition: 'Malaria',
      probability: 0.85,
      icd_code: 'B54',
      concordant_symptoms: ['fever', 'chills'],
    };
    expect(diag.probability).toBeGreaterThanOrEqual(0);
    expect(diag.probability).toBeLessThanOrEqual(1);
    expect(diag.icd_code).toBe('B54');
  });

  it('serializes and deserializes without data loss', () => {
    const diag: DifferentialDiagnosis = {
      condition: 'Typhoid fever',
      probability: 0.6,
      concordant_symptoms: ['fever', 'headache', 'abdominal pain'],
    };
    const json = JSON.stringify(diag);
    const restored: DifferentialDiagnosis = JSON.parse(json);
    expect(restored).toEqual(diag);
  });
});

// ─── Symptom ──────────────────────────────────────────────────────────────────

describe('Symptom', () => {
  it('constructs and serializes correctly', () => {
    const symptom: Symptom = {
      name: 'fever',
      severity: 'high',
      duration_days: 3,
    };
    const json = JSON.stringify(symptom);
    const restored: Symptom = JSON.parse(json);
    expect(restored).toEqual(symptom);
  });
});

// ─── DocumentSource ───────────────────────────────────────────────────────────

describe('DocumentSource', () => {
  it('constructs and serializes correctly', () => {
    const source: DocumentSource = {
      title: 'OMS AFRO Guidelines 2023',
      section: 'Chapter 3 — Malaria',
      excerpt: 'Artemisinin-based combination therapy is recommended...',
    };
    const json = JSON.stringify(source);
    const restored: DocumentSource = JSON.parse(json);
    expect(restored).toEqual(source);
  });
});

// ─── ChatMessage ──────────────────────────────────────────────────────────────

describe('ChatMessage', () => {
  it('constructs a user message', () => {
    const msg: ChatMessage = {
      id: 'msg-1',
      role: 'user',
      content: 'What is the treatment for malaria?',
      timestamp: '2024-01-01T10:00:00Z',
    };
    expect(msg.role).toBe('user');
    expect(msg.sources).toBeUndefined();
  });

  it('constructs an assistant message with sources', () => {
    const msg: ChatMessage = {
      id: 'msg-2',
      role: 'assistant',
      content: 'Artemisinin-based combination therapy is recommended.',
      sources: [{ title: 'OMS AFRO', section: 'Ch3', excerpt: '...' }],
      timestamp: '2024-01-01T10:00:01Z',
    };
    expect(msg.role).toBe('assistant');
    expect(msg.sources).toHaveLength(1);
  });

  it('serializes and deserializes without data loss', () => {
    const msg: ChatMessage = {
      id: 'msg-3',
      role: 'assistant',
      content: 'Take artemether-lumefantrine.',
      sources: [{ title: 'PNLP', section: 'Malaria', excerpt: 'ACT recommended' }],
      timestamp: '2024-01-01T10:00:02Z',
    };
    const json = JSON.stringify(msg);
    const restored: ChatMessage = JSON.parse(json);
    expect(restored).toEqual(msg);
  });
});

// ─── ChatSession ──────────────────────────────────────────────────────────────

describe('ChatSession', () => {
  it('constructs a session with messages and optional patient context', () => {
    const session: ChatSession = {
      id: 'session-1',
      messages: [],
      createdAt: '2024-01-01T09:00:00Z',
    };
    expect(session.messages).toHaveLength(0);
    expect(session.patientContext).toBeUndefined();
  });

  it('serializes and deserializes without data loss', () => {
    const session: ChatSession = {
      id: 'session-2',
      messages: [
        { id: 'm1', role: 'user', content: 'Hello', timestamp: '2024-01-01T09:01:00Z' },
      ],
      patientContext: {
        allergies: [],
        renalFailure: false,
        hepaticFailure: false,
        currentMedications: [],
      },
      createdAt: '2024-01-01T09:00:00Z',
    };
    const json = JSON.stringify(session);
    const restored: ChatSession = JSON.parse(json);
    expect(restored).toEqual(session);
  });
});

// ─── Consultation ─────────────────────────────────────────────────────────────

describe('Consultation', () => {
  it('constructs a one-shot consultation without patientId', () => {
    const consultation: Consultation = {
      id: 'c-001',
      symptoms: [{ name: 'fever', severity: 'high', duration_days: 2 }],
      diagnoses: [{ condition: 'Malaria', probability: 0.9, concordant_symptoms: ['fever'] }],
      alerts: [],
      llmUsed: 'qwen3',
      createdAt: '2024-01-01T08:00:00Z',
      isOneShot: true,
    };
    expect(consultation.patientId).toBeUndefined();
    expect(consultation.isOneShot).toBe(true);
  });

  it('serializes and deserializes without data loss', () => {
    const consultation: Consultation = {
      id: 'c-002',
      patientId: 'p-001',
      symptoms: [{ name: 'cough', severity: 'moderate', duration_days: 5 }],
      diagnoses: [
        { condition: 'Pneumonia', probability: 0.75, icd_code: 'J18', concordant_symptoms: ['cough'] },
      ],
      prescription: {
        antibiotic: 'Amoxicillin',
        dose_mg: 500,
        frequency: 'TID',
        duration_days: 7,
        route: 'oral',
        is_capped_to_adult_dose: false,
      },
      alerts: [],
      llmUsed: 'qwen3',
      createdAt: '2024-01-01T08:00:00Z',
      isOneShot: false,
    };
    const json = JSON.stringify(consultation);
    const restored: Consultation = JSON.parse(json);
    expect(restored).toEqual(consultation);
  });
});
