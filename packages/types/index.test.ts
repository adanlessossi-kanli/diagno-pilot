// Tests for shared TypeScript types — REQ-02, REQ-06, RBAC
import { describe, it, expect } from 'vitest';
import { ZodError } from 'zod';
import * as fc from 'fast-check';
import {
  AgeGroupSchema,
  AlertLevelSchema,
  UserRoleSchema,
  LocaleSchema,
  AuthUserSchema,
  SymptomSchema,
  DifferentialDiagnosisSchema,
  DocumentSourceSchema,
  PrescriptionSchema,
  SafetyAlertSchema,
  PatientProfileSchema,
  ConsultationSchema,
  ChatMessageSchema,
  ChatSessionSchema,
} from './index';
import type {
  AgeGroup,
  AlertLevel,
  UserRole,
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

// ─── Arbitraries ──────────────────────────────────────────────────────────────

const ageGroupArb = fc.constantFrom('neonatal', 'infant', 'child', 'adult');
const alertLevelArb = fc.constantFrom('critical', 'warning', 'info');
const userRoleArb = fc.constantFrom('admin', 'medecin', 'infirmière', 'guest');
const localeArb = fc.constantFrom('fr', 'en', 'fr-TG', 'fr-BJ');
const routeArb = fc.constantFrom('oral', 'IV', 'IM');
const alertTypeArb = fc.constantFrom('allergy', 'interaction', 'contraindication');
const chatRoleArb = fc.constantFrom('user', 'assistant');

const symptomArb = fc.record({
  name: fc.string({ minLength: 1 }),
  severity: fc.string({ minLength: 1 }),
  durationDays: fc.integer({ min: 0, max: 365 }),
});

const documentSourceArb = fc.record({
  documentId: fc.string(),
  title: fc.string({ minLength: 1 }),
  source: fc.string(),
  section: fc.string({ minLength: 1 }),
  excerpt: fc.string({ minLength: 1 }),
});

const differentialDiagnosisArb = fc.record({
  condition: fc.string({ minLength: 1 }),
  probability: fc.float({ min: 0, max: 1, noNaN: true }),
  icdCode: fc.option(fc.string({ minLength: 1 }), { nil: undefined }),
  concordantSymptoms: fc.array(fc.string()),
});

const prescriptionArb = fc.record({
  antibiotic: fc.string({ minLength: 1 }),
  doseMg: fc.float({ min: 0, max: Math.fround(1e6), noNaN: true, noDefaultInfinity: true }),
  dosePerKg: fc.option(fc.float({ min: 0, max: Math.fround(1e4), noNaN: true, noDefaultInfinity: true }), { nil: undefined }),
  frequency: fc.string({ minLength: 1 }),
  durationDays: fc.integer({ min: 1, max: 30 }),
  route: routeArb,
  isCappedToAdultDose: fc.boolean(),
});

const safetyAlertArb = fc.record({
  level: alertLevelArb,
  type: alertTypeArb,
  message: fc.string({ minLength: 1 }),
  affectedDrug: fc.option(fc.string({ minLength: 1 }), { nil: undefined }),
});

const patientProfileArb = fc.record({
  id: fc.option(fc.string({ minLength: 1 }), { nil: undefined }),
  fullName: fc.option(fc.string({ minLength: 1 }), { nil: undefined }),
  dateOfBirth: fc.option(fc.string({ minLength: 1 }), { nil: undefined }),
  weightKg: fc.option(fc.float({ min: 0, max: Math.fround(300), noNaN: true, noDefaultInfinity: true }), { nil: undefined }),
  ageGroup: fc.option(ageGroupArb, { nil: undefined }),
  allergies: fc.array(fc.string()),
  renalFailure: fc.boolean(),
  hepaticFailure: fc.boolean(),
  currentMedications: fc.array(fc.string()),
});

const chatMessageArb = fc.record({
  id: fc.string({ minLength: 1 }),
  role: chatRoleArb,
  content: fc.string(),
  sources: fc.option(fc.array(documentSourceArb), { nil: undefined }),
  timestamp: fc.string({ minLength: 1 }),
});

const chatSessionArb = fc.record({
  id: fc.string({ minLength: 1 }),
  messages: fc.array(chatMessageArb),
  patientContext: fc.option(patientProfileArb, { nil: undefined }),
  createdAt: fc.string({ minLength: 1 }),
});

const authUserArb = fc.record({
  id: fc.string({ minLength: 1 }),
  email: fc.string({ minLength: 1 }),
  fullName: fc.string({ minLength: 1 }),
  role: userRoleArb,
  locale: fc.option(localeArb, { nil: undefined }),
});

const evidenceCitationArb = fc.record({
  documentId: fc.string({ minLength: 1 }),
  title: fc.string({ minLength: 1 }),
  source: fc.string({ minLength: 1 }),
  excerpt: fc.string({ minLength: 1 }),
  page: fc.option(fc.integer({ min: 1, max: 500 }), { nil: undefined }),
});

const agentContributionArb = fc.record({
  agentName: fc.string({ minLength: 1 }),
  confidenceScore: fc.float({ min: 0, max: 1, noNaN: true }),
  partialDifferential: fc.array(fc.record({
    condition: fc.string({ minLength: 1 }),
    probability: fc.float({ min: 0, max: 1, noNaN: true }),
    icdCode: fc.option(fc.string({ minLength: 1 }), { nil: undefined }),
    matchingSymptoms: fc.array(fc.string()),
  })),
});

const consultationArb = fc.record({
  id: fc.string({ minLength: 1 }),
  patientId: fc.option(fc.string({ minLength: 1 }), { nil: undefined }),
  symptoms: fc.array(symptomArb),
  diagnoses: fc.array(differentialDiagnosisArb),
  prescription: fc.option(prescriptionArb, { nil: undefined }),
  alerts: fc.array(safetyAlertArb),
  llmUsed: fc.string({ minLength: 1 }),
  createdAt: fc.string({ minLength: 1 }),
  isOneShot: fc.boolean(),
  agentContributions: fc.array(agentContributionArb),
  evidenceCitations: fc.array(evidenceCitationArb),
});

// ─── Property 9: Zod schemas accept all valid objects ─────────────────────────
// Feature: code-quality — Validates: Requirements 5.1, 5.2

describe('Property 9: Zod schemas accept all valid objects', () => {
  it('SymptomSchema accepts all valid Symptom objects', () => {
    fc.assert(fc.property(symptomArb, (obj) => {
      expect(() => SymptomSchema.parse(obj)).not.toThrow();
    }), { numRuns: 100 });
  });

  it('DifferentialDiagnosisSchema accepts all valid DifferentialDiagnosis objects', () => {
    fc.assert(fc.property(differentialDiagnosisArb, (obj) => {
      expect(() => DifferentialDiagnosisSchema.parse(obj)).not.toThrow();
    }), { numRuns: 100 });
  });

  it('DocumentSourceSchema accepts all valid DocumentSource objects', () => {
    fc.assert(fc.property(documentSourceArb, (obj) => {
      expect(() => DocumentSourceSchema.parse(obj)).not.toThrow();
    }), { numRuns: 100 });
  });

  it('PrescriptionSchema accepts all valid Prescription objects', () => {
    fc.assert(fc.property(prescriptionArb, (obj) => {
      expect(() => PrescriptionSchema.parse(obj)).not.toThrow();
    }), { numRuns: 100 });
  });

  it('SafetyAlertSchema accepts all valid SafetyAlert objects', () => {
    fc.assert(fc.property(safetyAlertArb, (obj) => {
      expect(() => SafetyAlertSchema.parse(obj)).not.toThrow();
    }), { numRuns: 100 });
  });

  it('PatientProfileSchema accepts all valid PatientProfile objects', () => {
    fc.assert(fc.property(patientProfileArb, (obj) => {
      expect(() => PatientProfileSchema.parse(obj)).not.toThrow();
    }), { numRuns: 100 });
  });

  it('AuthUserSchema accepts all valid AuthUser objects', () => {
    fc.assert(fc.property(authUserArb, (obj) => {
      expect(() => AuthUserSchema.parse(obj)).not.toThrow();
    }), { numRuns: 100 });
  });

  it('ChatMessageSchema accepts all valid ChatMessage objects', () => {
    fc.assert(fc.property(chatMessageArb, (obj) => {
      expect(() => ChatMessageSchema.parse(obj)).not.toThrow();
    }), { numRuns: 100 });
  });

  it('ChatSessionSchema accepts all valid ChatSession objects', () => {
    fc.assert(fc.property(chatSessionArb, (obj) => {
      expect(() => ChatSessionSchema.parse(obj)).not.toThrow();
    }), { numRuns: 100 });
  });

  it('ConsultationSchema accepts all valid Consultation objects', () => {
    fc.assert(fc.property(consultationArb, (obj) => {
      expect(() => ConsultationSchema.parse(obj)).not.toThrow();
    }), { numRuns: 100 });
  });
});

// ─── Property 10: Zod schemas reject invalid objects ─────────────────────────
// Feature: code-quality — Validates: Requirements 5.3

describe('Property 10: Zod schemas reject invalid objects', () => {
  it('SymptomSchema rejects objects missing required fields', () => {
    // Missing duration_days (required number)
    fc.assert(fc.property(
      fc.record({ name: fc.string(), severity: fc.string() }),
      (obj) => {
        expect(() => SymptomSchema.parse(obj)).toThrow(ZodError);
      }
    ), { numRuns: 100 });
  });

  it('SymptomSchema rejects objects with wrong field types', () => {
    // durationDays must be a number, not a string
    fc.assert(fc.property(
      fc.record({
        name: fc.string(),
        severity: fc.string(),
        durationDays: fc.string(),
      }),
      (obj) => {
        expect(() => SymptomSchema.parse(obj)).toThrow(ZodError);
      }
    ), { numRuns: 100 });
  });

  it('DifferentialDiagnosisSchema rejects probability outside [0, 1]', () => {
    fc.assert(fc.property(
      fc.record({
        condition: fc.string({ minLength: 1 }),
        probability: fc.oneof(
          fc.float({ min: Math.fround(1.001), max: Math.fround(1e6), noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: Math.fround(-1e6), max: Math.fround(-0.001), noNaN: true, noDefaultInfinity: true }),
        ),
        concordantSymptoms: fc.array(fc.string()),
      }),
      (obj) => {
        expect(() => DifferentialDiagnosisSchema.parse(obj)).toThrow(ZodError);
      }
    ), { numRuns: 100 });
  });

  it('PrescriptionSchema rejects invalid route values', () => {
    fc.assert(fc.property(
      fc.record({
        antibiotic: fc.string({ minLength: 1 }),
        doseMg: fc.float({ min: 0, noNaN: true }),
        frequency: fc.string({ minLength: 1 }),
        durationDays: fc.integer({ min: 1 }),
        route: fc.string().filter(s => !['oral', 'IV', 'IM'].includes(s)),
        isCappedToAdultDose: fc.boolean(),
      }),
      (obj) => {
        expect(() => PrescriptionSchema.parse(obj)).toThrow(ZodError);
      }
    ), { numRuns: 100 });
  });

  it('SafetyAlertSchema rejects invalid level values', () => {
    fc.assert(fc.property(
      fc.record({
        level: fc.string().filter(s => !['critical', 'warning', 'info'].includes(s)),
        type: alertTypeArb,
        message: fc.string({ minLength: 1 }),
      }),
      (obj) => {
        expect(() => SafetyAlertSchema.parse(obj)).toThrow(ZodError);
      }
    ), { numRuns: 100 });
  });

  it('PatientProfileSchema rejects objects missing required array fields', () => {
    // Missing allergies, renalFailure, hepaticFailure, currentMedications
    fc.assert(fc.property(
      fc.record({ id: fc.string() }),
      (obj) => {
        expect(() => PatientProfileSchema.parse(obj)).toThrow(ZodError);
      }
    ), { numRuns: 100 });
  });

  it('AuthUserSchema rejects invalid role values', () => {
    fc.assert(fc.property(
      fc.record({
        id: fc.string({ minLength: 1 }),
        email: fc.string({ minLength: 1 }),
        fullName: fc.string({ minLength: 1 }),
        role: fc.string().filter(s => !['admin', 'medecin', 'infirmière', 'guest'].includes(s)),
      }),
      (obj) => {
        expect(() => AuthUserSchema.parse(obj)).toThrow(ZodError);
      }
    ), { numRuns: 100 });
  });
});

// ─── Property 11: Zod schema round-trip serialization ────────────────────────
// Feature: code-quality — Validates: Requirements 7.1

describe('Property 11: Zod schema round-trip serialization', () => {
  it('SymptomSchema round-trips through JSON serialization', () => {
    fc.assert(fc.property(symptomArb, (obj) => {
      const parsed = SymptomSchema.parse(JSON.parse(JSON.stringify(obj)));
      expect(JSON.stringify(parsed)).toEqual(JSON.stringify(obj));
    }), { numRuns: 100 });
  });

  it('DifferentialDiagnosisSchema round-trips through JSON serialization', () => {
    fc.assert(fc.property(differentialDiagnosisArb, (obj) => {
      const serialized = JSON.stringify(obj);
      const parsed = DifferentialDiagnosisSchema.parse(JSON.parse(serialized));
      expect(JSON.stringify(parsed)).toEqual(serialized);
    }), { numRuns: 100 });
  });

  it('PatientProfileSchema round-trips through JSON serialization', () => {
    fc.assert(fc.property(patientProfileArb, (obj) => {
      const serialized = JSON.stringify(obj);
      const parsed = PatientProfileSchema.parse(JSON.parse(serialized));
      expect(JSON.stringify(parsed)).toEqual(serialized);
    }), { numRuns: 100 });
  });

  it('PrescriptionSchema round-trips through JSON serialization', () => {
    fc.assert(fc.property(prescriptionArb, (obj) => {
      const serialized = JSON.stringify(obj);
      const parsed = PrescriptionSchema.parse(JSON.parse(serialized));
      expect(JSON.stringify(parsed)).toEqual(serialized);
    }), { numRuns: 100 });
  });

  it('ChatSessionSchema round-trips through JSON serialization', () => {
    fc.assert(fc.property(chatSessionArb, (obj) => {
      const serialized = JSON.stringify(obj);
      const parsed = ChatSessionSchema.parse(JSON.parse(serialized));
      expect(JSON.stringify(parsed)).toEqual(serialized);
    }), { numRuns: 100 });
  });

  it('ConsultationSchema round-trips through JSON serialization', () => {
    fc.assert(fc.property(consultationArb, (obj) => {
      const serialized = JSON.stringify(obj);
      const parsed = ConsultationSchema.parse(JSON.parse(serialized));
      expect(JSON.stringify(parsed)).toEqual(serialized);
    }), { numRuns: 100 });
  });
});

// ─── Existing unit tests ──────────────────────────────────────────────────────

describe('UserRole', () => {
  it('contains exactly the 4 valid RBAC roles', () => {
    const validRoles: UserRole[] = ['admin', 'medecin', 'infirmière', 'guest'];
    expect(validRoles).toHaveLength(4);
    expect(validRoles).toContain('admin');
    expect(validRoles).toContain('medecin');
    expect(validRoles).toContain('infirmière');
    expect(validRoles).toContain('guest');
  });

  it('does not include legacy role pharmacien', () => {
    const validRoles: UserRole[] = ['admin', 'medecin', 'infirmière', 'guest'];
    expect(validRoles).not.toContain('pharmacien');
  });
});

describe('AgeGroup', () => {
  it('accepts all valid string literals', () => {
    const values: AgeGroup[] = ['neonatal', 'infant', 'child', 'adult'];
    expect(values).toHaveLength(4);
  });
});

describe('AlertLevel', () => {
  it('accepts all valid string literals', () => {
    const values: AlertLevel[] = ['critical', 'warning', 'info'];
    expect(values).toHaveLength(3);
  });
});

describe('Prescription', () => {
  it('accepts oral route', () => {
    const p: Prescription = {
      antibiotic: 'Amoxicillin',
      doseMg: 500,
      frequency: 'TID',
      durationDays: 7,
      route: 'oral',
      isCappedToAdultDose: false,
    };
    expect(p.route).toBe('oral');
  });

  it('serializes and deserializes without data loss', () => {
    const p: Prescription = {
      antibiotic: 'Amoxicillin',
      doseMg: 250,
      dosePerKg: 25,
      frequency: 'BID',
      durationDays: 5,
      route: 'oral',
      isCappedToAdultDose: true,
    };
    const json = JSON.stringify(p);
    const restored: Prescription = JSON.parse(json);
    expect(restored).toEqual(p);
  });
});

describe('PatientProfile', () => {
  it('constructs a minimal profile with required fields', () => {
    const profile: PatientProfile = {
      allergies: [],
      renalFailure: false,
      hepaticFailure: false,
      currentMedications: [],
    };
    expect(profile.allergies).toEqual([]);
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
    expect(profile.ageGroup).toBe('adult');
  });
});

describe('SafetyAlert', () => {
  it('constructs a critical allergy alert', () => {
    const alert: SafetyAlert = {
      level: 'critical',
      type: 'allergy',
      message: 'Patient is allergic to penicillin',
      affectedDrug: 'Amoxicillin',
    };
    expect(alert.level).toBe('critical');
  });
});

describe('DifferentialDiagnosis', () => {
  it('constructs a diagnosis entry with optional icd_code', () => {
    const diag: DifferentialDiagnosis = {
      condition: 'Malaria',
      probability: 0.85,
      icdCode: 'B54',
      concordantSymptoms: ['fever', 'chills'],
    };
    expect(diag.probability).toBeGreaterThanOrEqual(0);
    expect(diag.probability).toBeLessThanOrEqual(1);
  });
});

describe('Symptom', () => {
  it('constructs and serializes correctly', () => {
    const symptom: Symptom = { name: 'fever', severity: 'high', durationDays: 3 };
    const restored: Symptom = JSON.parse(JSON.stringify(symptom));
    expect(restored).toEqual(symptom);
  });
});

describe('DocumentSource', () => {
  it('constructs and serializes correctly', () => {
    const source: DocumentSource = {
      title: 'OMS AFRO Guidelines 2023',
      section: 'Chapter 3 — Malaria',
      excerpt: 'Artemisinin-based combination therapy is recommended...',
    };
    expect(JSON.parse(JSON.stringify(source))).toEqual(source);
  });
});

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
});

describe('ChatSession', () => {
  it('constructs a session with messages', () => {
    const session: ChatSession = {
      id: 'session-1',
      messages: [],
      createdAt: '2024-01-01T09:00:00Z',
    };
    expect(session.messages).toHaveLength(0);
  });
});

describe('Consultation', () => {
  it('constructs a one-shot consultation without patientId', () => {
    const consultation: Consultation = {
      id: 'c-001',
      symptoms: [{ name: 'fever', severity: 'high', durationDays: 2 }],
      diagnoses: [{ condition: 'Malaria', probability: 0.9, concordantSymptoms: ['fever'] }],
      alerts: [],
      llmUsed: 'qwen3',
      createdAt: '2024-01-01T08:00:00Z',
      isOneShot: true,
    };
    expect(consultation.patientId).toBeUndefined();
    expect(consultation.isOneShot).toBe(true);
  });
});
