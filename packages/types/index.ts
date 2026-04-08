// Shared TypeScript types for Diagno-Pilot — derived from Zod schemas
// REQ-02, REQ-03, REQ-06, REQ-08, REQ-09
import { z } from 'zod';

// ─── Primitive enums ──────────────────────────────────────────────────────────

/** Age group for pediatric/adult dosing calculations (REQ-06, REQ-08) */
export const AgeGroupSchema = z.enum(['neonatal', 'infant', 'child', 'adult']);
export type AgeGroup = z.infer<typeof AgeGroupSchema>;

/** Severity level for safety alerts (REQ-09) */
export const AlertLevelSchema = z.enum(['critical', 'warning', 'info']);
export type AlertLevel = z.infer<typeof AlertLevelSchema>;

/** User roles controlling feature access (REQ-01, RBAC) */
export const UserRoleSchema = z.enum(['admin', 'medecin', 'infirmière', 'guest']);
export type UserRole = z.infer<typeof UserRoleSchema>;

/** Supported application locales (REQ-12, REQ-i18n-1.6, REQ-i18n-9.4) */
export const LocaleSchema = z.enum(['fr', 'en', 'fr-TG', 'fr-BJ']);
export type Locale = z.infer<typeof LocaleSchema>;

// ─── Object schemas ───────────────────────────────────────────────────────────

/** Authenticated user returned by /auth/me and stored in AuthContext */
export const AuthUserSchema = z.object({
  id: z.string(),
  email: z.string(),
  /** Display name */
  fullName: z.string(),
  role: UserRoleSchema,
  locale: LocaleSchema.optional(),
});
export type AuthUser = z.infer<typeof AuthUserSchema>;

/** A clinical symptom reported by or observed in the patient (REQ-02) */
export const SymptomSchema = z.object({
  name: z.string(),
  severity: z.string(),
  duration_days: z.number(),
});
export type Symptom = z.infer<typeof SymptomSchema>;

/** A differential diagnosis entry with probability score (REQ-02) */
export const DifferentialDiagnosisSchema = z.object({
  condition: z.string(),
  /** Probability score between 0 and 1 */
  probability: z.number().min(0).max(1),
  /** ICD-10 code, when available */
  icd_code: z.string().optional(),
  concordant_symptoms: z.array(z.string()),
});
export type DifferentialDiagnosis = z.infer<typeof DifferentialDiagnosisSchema>;

/** Reference to a source document used in a RAG response (REQ-04) */
export const HighlightInfoSchema = z.object({
  bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  page: z.number(),
});
export type HighlightInfo = z.infer<typeof HighlightInfoSchema>;

export const DocumentSourceSchema = z.object({
  document_id: z.string().optional().default(''),
  /** Document title or identifier */
  title: z.string(),
  source: z.string().optional().default(''),
  section: z.string().optional(),
  excerpt: z.string().optional(),
  page: z.number().optional(),
  highlight: HighlightInfoSchema.optional(),
  confidence_score: z.number().optional(),
});
export type DocumentSource = z.infer<typeof DocumentSourceSchema>;

/** Antibiotic prescription with dosing details (REQ-03, REQ-08) */
export const PrescriptionSchema = z.object({
  antibiotic: z.string(),
  dose_mg: z.number(),
  /** Weight-based dose in mg/kg, used for pediatric patients */
  dose_per_kg: z.number().optional(),
  frequency: z.string(),
  duration_days: z.number(),
  /** Route of administration */
  route: z.enum(['oral', 'IV', 'IM']),
  /** True when the calculated dose has been capped to the maximum adult dose */
  is_capped_to_adult_dose: z.boolean(),
});
export type Prescription = z.infer<typeof PrescriptionSchema>;

/** Safety alert for allergies, interactions, or contraindications (REQ-09) */
export const SafetyAlertSchema = z.object({
  level: AlertLevelSchema,
  /** Category of the alert */
  type: z.enum(['allergy', 'interaction', 'contraindication']),
  message: z.string(),
  affected_drug: z.string().optional(),
});
export type SafetyAlert = z.infer<typeof SafetyAlertSchema>;

/** Patient clinical profile used to personalise recommendations (REQ-06) */
export const PatientProfileSchema = z.object({
  id: z.string().optional(),
  fullName: z.string().optional(),
  /** ISO date string (YYYY-MM-DD) */
  dateOfBirth: z.string().optional(),
  weightKg: z.number().optional(),
  ageGroup: AgeGroupSchema.optional(),
  allergies: z.array(z.string()),
  renalFailure: z.boolean(),
  hepaticFailure: z.boolean(),
  currentMedications: z.array(z.string()),
});
export type PatientProfile = z.infer<typeof PatientProfileSchema>;

/** Citation of evidence linking a diagnosis to a source document (REQ-16.7) */
export const EvidenceCitationSchema = z.object({
  documentId: z.string(),
  title: z.string(),
  source: z.string(),
  excerpt: z.string(),
  page: z.number().nullable().optional(),
});
export type EvidenceCitation = z.infer<typeof EvidenceCitationSchema>;

/** Contribution of a specialist agent to a diagnostic session (REQ-16.7) */
export const AgentContributionSchema = z.object({
  agentName: z.string(),
  confidenceScore: z.number().min(0).max(1),
  partialDifferential: z.array(z.object({
    condition: z.string(),
    probability: z.number().min(0).max(1),
    icdCode: z.string().nullable().optional(),
    matchingSymptoms: z.array(z.string()).optional().default([]),
  })),
});
export type AgentContribution = z.infer<typeof AgentContributionSchema>;

/** A single consultation (guided mode) linking symptoms, diagnoses and prescription (REQ-02, REQ-03) */
export const ConsultationSchema = z.object({
  id: z.string(),
  /** Undefined for one-shot consultations */
  patientId: z.string().optional(),
  symptoms: z.array(SymptomSchema),
  diagnoses: z.array(DifferentialDiagnosisSchema),
  prescription: PrescriptionSchema.optional(),
  alerts: z.array(SafetyAlertSchema),
  /** Identifier of the LLM that generated the response, e.g. 'qwen3' | 'gpt5' */
  llmUsed: z.string(),
  /** ISO 8601 timestamp */
  createdAt: z.string(),
  /** True when the consultation was performed without a patient record */
  isOneShot: z.boolean(),
  /** MCP session identifier linking to agent results */
  mcpSessionId: z.string().optional(),
  /** Contributions from each specialist agent */
  agentContributions: z.array(AgentContributionSchema).optional().default([]),
  /** Evidence citations used to produce the diagnosis */
  evidenceCitations: z.array(EvidenceCitationSchema).optional().default([]),
});
export type Consultation = z.infer<typeof ConsultationSchema>;

/** A single message in the conversational Q&A interface (REQ-04) */
export const ChatMessageSchema = z.object({
  id: z.string(),
  role: z.enum(['user', 'assistant']),
  content: z.string(),
  /** Source documents cited in the response */
  sources: z.array(DocumentSourceSchema).optional(),
  /** ISO 8601 timestamp */
  timestamp: z.string(),
});
export type ChatMessage = z.infer<typeof ChatMessageSchema>;

/** A conversational chat session with optional patient context (REQ-04) */
export const ChatSessionSchema = z.object({
  id: z.string(),
  messages: z.array(ChatMessageSchema),
  patientContext: PatientProfileSchema.optional(),
  /** ISO 8601 timestamp */
  createdAt: z.string(),
});
export type ChatSession = z.infer<typeof ChatSessionSchema>;
