// Shared TypeScript types for Diagno-Pilot
// REQ-02, REQ-03, REQ-06, REQ-08, REQ-09

// ─── Primitive types ──────────────────────────────────────────────────────────

/** Age group for pediatric/adult dosing calculations (REQ-06, REQ-08) */
export type AgeGroup = 'neonatal' | 'infant' | 'child' | 'adult';

/** Severity level for safety alerts (REQ-09) */
export type AlertLevel = 'critical' | 'warning' | 'info';

/** User roles controlling feature access (REQ-01) */
export type UserRole = 'medecin' | 'pharmacien' | 'admin';

/** Supported application locales (REQ-12) */
export type Locale = 'fr' | 'en';

/** Authenticated user returned by /auth/me and stored in AuthContext */
export interface AuthUser {
  id: string;
  email: string;
  /** Display name */
  fullName: string;
  role: UserRole;
  locale?: Locale;
}

// ─── Clinical entities ────────────────────────────────────────────────────────

/** A clinical symptom reported by or observed in the patient (REQ-02) */
export interface Symptom {
  name: string;
  severity: string;
  duration_days: number;
}

/** A differential diagnosis entry with probability score (REQ-02) */
export interface DifferentialDiagnosis {
  condition: string;
  /** Probability score between 0 and 1 */
  probability: number;
  /** ICD-10 code, when available */
  icd_code?: string;
  concordant_symptoms: string[];
}

/** Reference to a source document used in a RAG response (REQ-04) */
export interface DocumentSource {
  /** Document title or identifier */
  title: string;
  section: string;
  excerpt: string;
}

/** Antibiotic prescription with dosing details (REQ-03, REQ-08) */
export interface Prescription {
  antibiotic: string;
  dose_mg: number;
  /** Weight-based dose in mg/kg, used for pediatric patients */
  dose_per_kg?: number;
  frequency: string;
  duration_days: number;
  /** Route of administration */
  route: 'oral' | 'IV' | 'IM';
  /** True when the calculated dose has been capped to the maximum adult dose */
  is_capped_to_adult_dose: boolean;
}

/** Safety alert for allergies, interactions, or contraindications (REQ-09) */
export interface SafetyAlert {
  level: AlertLevel;
  /** Category of the alert */
  type: 'allergy' | 'interaction' | 'contraindication';
  message: string;
  affected_drug?: string;
}

// ─── Patient & session entities ───────────────────────────────────────────────

/** Patient clinical profile used to personalise recommendations (REQ-06) */
export interface PatientProfile {
  id?: string;
  fullName?: string;
  /** ISO date string (YYYY-MM-DD) */
  dateOfBirth?: string;
  weightKg?: number;
  ageGroup?: AgeGroup;
  allergies: string[];
  renalFailure: boolean;
  hepaticFailure: boolean;
  currentMedications: string[];
}

/** A single consultation (guided mode) linking symptoms, diagnoses and prescription (REQ-02, REQ-03) */
export interface Consultation {
  id: string;
  /** Undefined for one-shot consultations */
  patientId?: string;
  symptoms: Symptom[];
  diagnoses: DifferentialDiagnosis[];
  prescription?: Prescription;
  alerts: SafetyAlert[];
  /** Identifier of the LLM that generated the response, e.g. 'qwen3' | 'gpt5' */
  llmUsed: string;
  /** ISO 8601 timestamp */
  createdAt: string;
  /** True when the consultation was performed without a patient record */
  isOneShot: boolean;
}

/** A single message in the conversational Q&A interface (REQ-04) */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  /** Source documents cited in the response */
  sources?: DocumentSource[];
  /** ISO 8601 timestamp */
  timestamp: string;
}

/** A conversational chat session with optional patient context (REQ-04) */
export interface ChatSession {
  id: string;
  messages: ChatMessage[];
  patientContext?: PatientProfile;
  /** ISO 8601 timestamp */
  createdAt: string;
}
