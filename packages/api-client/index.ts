// HTTP API client for Diagno-Pilot
// Covers all backend endpoints: /auth, /chat, /diagnose, /patients, /documents, /files, /alerts
// REQ-01 through REQ-09

import type { ZodSchema } from 'zod';
import { ZodError, z } from 'zod';
import type {
  AuthUser,
  PatientProfile,
  Consultation,
  ChatMessage,
  ChatSession,
  Symptom,
  DifferentialDiagnosis,
  Prescription,
  SafetyAlert,
  DocumentSource,
  EvidenceCitation,
  AgentContribution,
} from '@diagno-pilot/types';
import {
  AuthUserSchema,
  PatientProfileSchema,
  ConsultationSchema,
  DifferentialDiagnosisSchema,
  DocumentSourceSchema,
  EvidenceCitationSchema,
  AgentContributionSchema,
} from '@diagno-pilot/types';

// ─── Response types ───────────────────────────────────────────────────────────

// Re-export AuthUser from @diagno-pilot/types for consumers of this package
export type { AuthUser } from '@diagno-pilot/types';

export interface LoginResponse {
  token_type: string;
  expires_in: number;
  user: {
    id: string;
    email: string;
    fullName: string;
    role: string;
    locale?: string;
  };
}

export interface DiagnosisResponse {
  sessionId: string;
  diagnoses: {
    condition: string;
    probability: number;
    icdCode?: string;
    matchingSymptoms: string[];
    concordantSymptoms: string[]; // alias kept for UI compatibility
  }[];
  // llmUsed and sources are not returned by /diagnose/symptoms — they come
  // from the RAG chat endpoint. Kept optional so UI code can guard safely.
  llmUsed?: string;
  sources?: DocumentSource[];
  /** Warning when fallback LLM was used */
  fallbackWarning?: string;
  /** Warning when one or more agents were degraded/omitted */
  degradedWarning?: string;
  /** True when any warning is present */
  warningsPresent?: boolean;
  /** Global confidence score (weighted average) */
  confidenceScore?: number;
  /** Contributions from each specialist agent */
  agentContributions?: AgentContribution[];
  /** Evidence citations backing the diagnoses */
  evidenceCitations?: EvidenceCitation[];
}

export interface PrescriptionResponse {
  prescription: Prescription;
  alerts: SafetyAlert[];
  llmUsed: string;
  sources: DocumentSource[];
}

export interface DiagnoseSession {
  id: string;
  symptoms: Symptom[];
  diagnoses: DifferentialDiagnosis[];
  prescription?: Prescription;
  alerts: SafetyAlert[];
  createdAt: string;
}

export interface PatientDocument {
  id: string;
  title: string;
  source: string;
  s3Key: string;
  originalName: string;
  sizeBytes: number;
  indexedAt?: string;
  createdAt: string;
  chunkCount?: number;
}

export interface UploadDocumentResponse {
  id: string;
  title: string;
  chunkCount: number;
  createdAt: string;
}

export interface PatientFile {
  id: string;
  patientId: string;
  fileType: string;
  originalName: string;
  sizeBytes: number;
  createdAt: string;
}

export interface UploadFileResponse {
  fileId: string;
  file: PatientFile;
}

export interface FileUrlResponse {
  url: string;
  expiresAt: string;
}

export interface AlertCheckResponse {
  alerts: SafetyAlert[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface ApiError {
  status: number;
  message: string;
  detail?: unknown;
}

// ─── Local Zod schemas for api-client response types ─────────────────────────

const DiagnosisResponseSchema = z.object({
  sessionId: z.string(),
  diagnoses: z.array(z.object({
    condition: z.string(),
    probability: z.number().min(0).max(1),
    icdCode: z.string().nullish().transform((v) => v ?? undefined),
    matchingSymptoms: z.array(z.string()).optional().default([]),
    concordantSymptoms: z.array(z.string()).optional().default([]),
  })),
  llmUsed: z.string().optional(),
  sources: z.array(DocumentSourceSchema).optional(),
  fallbackWarning: z.string().optional(),
  degradedWarning: z.string().optional(),
  warningsPresent: z.boolean().optional(),
  confidenceScore: z.number().optional(),
  agentContributions: z.array(AgentContributionSchema).optional().default([]),
  evidenceCitations: z.array(EvidenceCitationSchema).optional().default([]),
});

const PaginatedPatientResponseSchema = z.object({
  items: z.array(PatientProfileSchema),
  total: z.number(),
  page: z.number(),
  pageSize: z.number(),
});

const PaginatedConsultationResponseSchema = z.object({
  items: z.array(ConsultationSchema),
  total: z.number(),
  page: z.number(),
  pageSize: z.number(),
});

// ─── ApiValidationError ───────────────────────────────────────────────────────

export class ApiValidationError extends Error {
  constructor(
    public readonly zodError: ZodError,
    public readonly rawData: unknown,
  ) {
    super(`API response validation failed: ${zodError.message}`);
    this.name = 'ApiValidationError';
  }
}

// ─── normalizeKeys ────────────────────────────────────────────────────────────

/** Recursively converts snake_case object keys to camelCase. Handles nested objects and arrays. */
export function normalizeKeys(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(normalizeKeys);
  }
  if (value !== null && typeof value === 'object') {
    const result: Record<string, unknown> = {};
    for (const [key, val] of Object.entries(value as Record<string, unknown>)) {
      const camelKey = key.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
      result[camelKey] = normalizeKeys(val);
    }
    return result;
  }
  return value;
}

// ─── Internal helpers ─────────────────────────────────────────────────────────

export async function parseResponse<T>(res: Response, schema?: ZodSchema<T>): Promise<T> {
  const contentType = res.headers.get('content-type') ?? '';
  const isJson = contentType.includes('application/json');

  if (!res.ok) {
    const detail = isJson ? await res.json().catch(() => undefined) : await res.text().catch(() => undefined);
    const err: ApiError = {
      status: res.status,
      message: (detail as { detail?: string })?.detail ?? res.statusText,
      detail,
    };
    throw err;
  }

  if (res.status === 204 || !isJson) {
    return undefined as unknown as T;
  }

  const data = await res.json();

  if (schema) {
    const normalized = normalizeKeys(data);
    const result = schema.safeParse(normalized);
    if (!result.success) {
      throw new ApiValidationError(result.error, normalized);
    }
    return result.data;
  }

  return data as T;
}

// ─── Factory ──────────────────────────────────────────────────────────────────

/** Serialize a frontend PatientProfile to the backend snake_case shape. */
function serializePatientProfile(p: PatientProfile | null | undefined): Record<string, unknown> | null {
  if (!p) return null;
  return {
    full_name: p.fullName ?? null,
    date_of_birth: (p as unknown as { dateOfBirth?: string }).dateOfBirth ?? null,
    weight_kg: (p as unknown as { weightKg?: number }).weightKg ?? null,
    age_group: (p as unknown as { ageGroup?: string }).ageGroup ?? null,
    allergies: p.allergies ?? [],
    comorbidities: {
      renal_failure: (p as unknown as { renalFailure?: boolean }).renalFailure ?? false,
      hepatic_failure: (p as unknown as { hepaticFailure?: boolean }).hepaticFailure ?? false,
    },
    current_medications: (p as unknown as { currentMedications?: string[] }).currentMedications ?? [],
  };
}

// ─── CSRF helper ─────────────────────────────────────────────────────────────

/**
 * Reads the `csrf_token` value from `document.cookie`.
 * Returns an empty string in non-browser environments (e.g. SSR, tests without jsdom).
 */
export function getCsrfToken(): string {
  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : '';
}

// ─── Factory ──────────────────────────────────────────────────────────────────

/**
 * Creates a typed API client bound to a base URL.
 * Auth is handled via httpOnly cookies; CSRF token is read from the `csrf_token` cookie.
 *
 * @param baseUrl - Root URL of the FastAPI backend, e.g. "http://localhost:8000"
 * @param _getToken - Deprecated. Auth is cookie-based. Remove when updating callers.
 * @param getLocale - Optional getter for the active locale; injected as `Accept-Language` header (REQ-7.3, REQ-6.3).
 */
export function createApiClient(
  baseUrl: string,
  _getToken?: () => string | null,
  getLocale?: () => string,
) {
  const base = baseUrl.replace(/\/$/, '');

  function headers(extra?: Record<string, string>): Record<string, string> {
    const locale = getLocale?.();
    return {
      'Content-Type': 'application/json',
      ...(locale ? { 'Accept-Language': locale } : {}),
      ...extra,
    };
  }

  function csrfHeaders(extra?: Record<string, string>): Record<string, string> {
    const csrf = getCsrfToken();
    return headers({
      ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
      ...extra,
    });
  }

  function get<T>(path: string, signal?: AbortSignal): Promise<T> {
    return fetch(`${base}${path}`, { method: 'GET', headers: headers(), credentials: 'include', signal }).then(parseResponse<T>);
  }

  function post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return fetch(`${base}${path}`, {
      method: 'POST',
      headers: csrfHeaders(),
      credentials: 'include',
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    }).then(parseResponse<T>);
  }

  function put<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return fetch(`${base}${path}`, {
      method: 'PUT',
      headers: csrfHeaders(),
      credentials: 'include',
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    }).then(parseResponse<T>);
  }

  function del<T>(path: string, signal?: AbortSignal): Promise<T> {
    return fetch(`${base}${path}`, { method: 'DELETE', headers: csrfHeaders(), credentials: 'include', signal }).then(parseResponse<T>);
  }

  function postForm<T>(path: string, formData: FormData, signal?: AbortSignal): Promise<T> {
    const csrf = getCsrfToken();
    return fetch(`${base}${path}`, {
      method: 'POST',
      headers: csrf ? { 'X-CSRF-Token': csrf } : {},
      credentials: 'include',
      body: formData,
      signal,
    }).then(parseResponse<T>);
  }

  // ─── Auth (/api/v1/auth) ────────────────────────────────────────────────────

  const auth = {
    /** REQ-01 — Authenticate and receive a JWT token */
    login(email: string, password: string, signal?: AbortSignal): Promise<LoginResponse> {
      const form = new URLSearchParams();
      form.append('username', email);
      form.append('password', password);
      // Use the BFF proxy (/api/auth/login) so Set-Cookie headers are relayed
      // on the same origin as the frontend — avoids cross-origin cookie issues.
      return fetch(`${base}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        credentials: 'include',
        body: form.toString(),
        signal,
      }).then(parseResponse<LoginResponse>);
    },

    /** REQ-01 — Invalidate the current session */
    logout(signal?: AbortSignal): Promise<void> {
      const csrf = getCsrfToken();
      return fetch(`${base}/api/auth/logout`, {
        method: 'POST',
        headers: { ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
        credentials: 'include',
        signal,
      }).then(parseResponse<void>);
    },

    /** REQ-01 — Retrieve the currently authenticated user */
    me(signal?: AbortSignal): Promise<AuthUser> {
      return fetch(`${base}/api/auth/me`, {
        method: 'GET',
        headers: {},
        credentials: 'include',
        signal,
      }).then((res) => parseResponse(res, AuthUserSchema));
    },
  };

  // ─── Chat (/api/v1/chat) ────────────────────────────────────────────────────

  const chat = {
    /** REQ-04 — Send a message in a chat session */
    async sendMessage(
      sessionId: string,
      content: string,
      patientContext?: PatientProfile,
      signal?: AbortSignal,
    ): Promise<ChatMessage> {
      // Backend returns { session_id, answer, sources, llm_used } — map to ChatMessage
      const raw = await post<{ session_id: string; answer: string; sources: DocumentSource[]; llm_used: string }>(
        '/api/v1/chat/message',
        {
          session_id: sessionId,
          message: content,
          patient_context: serializePatientProfile(patientContext),
        },
        signal,
      );
      return {
        id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        role: 'assistant',
        content: raw.answer,
        sources: raw.sources,
        timestamp: new Date().toISOString(),
      };
    },

    /** REQ-04 — Retrieve the full message history for a session */
    getHistory(sessionId: string, signal?: AbortSignal): Promise<ChatSession> {
      return get<ChatSession>(`/api/v1/chat/history/${encodeURIComponent(sessionId)}`, signal);
    },
  };

  // ─── Diagnose (/api/v1/diagnose) ────────────────────────────────────────────

  const diagnose = {
    /** REQ-02 — Submit symptoms and receive differential diagnoses */
    getSymptomsDiagnosis(
      symptoms: Symptom[],
      patientProfile?: PatientProfile,
      signal?: AbortSignal,
    ): Promise<DiagnosisResponse> {
      // Backend returns { session_id, diagnoses } — no llmUsed/sources at this endpoint
      return fetch(`${base}/api/v1/diagnose/symptoms`, {
        method: 'POST',
        headers: csrfHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          symptoms,
          patient_profile: serializePatientProfile(patientProfile),
        }),
        signal,
      }).then((res) => parseResponse<DiagnosisResponse>(res, DiagnosisResponseSchema as ZodSchema<DiagnosisResponse>));
    },

    /** REQ-03 — Request an antibiotic prescription for a given diagnosis */
    getPrescription(
      diagnosisId: string,
      patientProfile: PatientProfile,
      signal?: AbortSignal,
    ): Promise<PrescriptionResponse> {
      return post<PrescriptionResponse>('/api/v1/diagnose/prescription', {
        antibiotic: diagnosisId,
        patient_profile: serializePatientProfile(patientProfile),
      }, signal);
    },

    /** REQ-03 — List available antibiotic protocol keys */
    listAntibiotics(signal?: AbortSignal): Promise<string[]> {
      return get<string[]>('/api/v1/diagnose/antibiotics', signal);
    },

    /** REQ-02, REQ-03 — Retrieve a full diagnose session by ID */
    getSession(sessionId: string, signal?: AbortSignal): Promise<DiagnoseSession> {
      return get<DiagnoseSession>(`/api/v1/diagnose/session/${encodeURIComponent(sessionId)}`, signal);
    },

    /** REQ-16.8 — List the authenticated practitioner's consultation history (paginated) */
    listMyConsultations(
      page = 1,
      pageSize = 20,
      signal?: AbortSignal,
    ): Promise<PaginatedResponse<Consultation>> {
      return fetch(`${base}/api/v1/consultations/me?page=${page}&page_size=${pageSize}`, {
        method: 'GET',
        headers: headers(),
        credentials: 'include',
        signal,
      }).then((res) => parseResponse(res, PaginatedConsultationResponseSchema)) as Promise<PaginatedResponse<Consultation>>;
    },
  };

  // ─── Patients (/api/v1/patients) ────────────────────────────────────────────

  const patients = {
    /** REQ-06 — List patients with pagination (REQ 8.1, 8.2, 8.3) */
    listPatients(page = 1, pageSize = 20, signal?: AbortSignal): Promise<PaginatedResponse<PatientProfile>> {
      return fetch(`${base}/api/v1/patients?page=${page}&page_size=${pageSize}`, {
        method: 'GET',
        headers: headers(),
        credentials: 'include',
        signal,
      }).then((res) => parseResponse(res, PaginatedPatientResponseSchema));
    },

    /** Convenience: fetch all patients from page 1 and return the items array directly. */
    async listAllPatients(signal?: AbortSignal): Promise<PatientProfile[]> {
      const result = await get<PaginatedResponse<PatientProfile>>(
        `/api/v1/patients?page=1&page_size=100`,
        signal,
      );
      return result.items;
    },

    /** REQ-06 — Create a new patient record */
    createPatient(data: Omit<PatientProfile, 'id'>, signal?: AbortSignal): Promise<PatientProfile> {
      return post<PatientProfile>('/api/v1/patients', data, signal);
    },

    /** REQ-06 — Retrieve a single patient by ID */
    getPatient(id: string, signal?: AbortSignal): Promise<PatientProfile> {
      return fetch(`${base}/api/v1/patients/${encodeURIComponent(id)}`, {
        method: 'GET',
        headers: headers(),
        credentials: 'include',
        signal,
      }).then((res) => parseResponse(res, PatientProfileSchema));
    },

    /** REQ-06 — Update an existing patient record */
    updatePatient(id: string, data: Partial<PatientProfile>, signal?: AbortSignal): Promise<PatientProfile> {
      return put<PatientProfile>(`/api/v1/patients/${encodeURIComponent(id)}`, data, signal);
    },

    /** REQ-07 — List all consultations for a patient */
    listConsultations(patientId: string, signal?: AbortSignal): Promise<Consultation[]> {
      return get<Consultation[]>(`/api/v1/patients/${encodeURIComponent(patientId)}/consultations`, signal);
    },

    /** REQ-07 — Create a new consultation linked to a patient */
    createConsultation(
      patientId: string,
      data: Omit<Consultation, 'id' | 'createdAt'>,
      signal?: AbortSignal,
    ): Promise<Consultation> {
      return post<Consultation>(
        `/api/v1/patients/${encodeURIComponent(patientId)}/consultations`,
        data,
        signal,
      );
    },
  };

  // ─── Documents (/api/v1/documents) ──────────────────────────────────────────

  const documents = {
    /**
     * REQ-05 — Upload and index a medical reference document.
     * @param file     - The file to upload (PDF, DOCX, TXT, CSV)
     * @param metadata - Optional metadata (title, source)
     */
    uploadDocument(
      file: File,
      metadata?: { title?: string; source?: string },
      signal?: AbortSignal,
    ): Promise<UploadDocumentResponse> {
      const form = new FormData();
      form.append('file', file);
      if (metadata?.title) form.append('title', metadata.title);
      if (metadata?.source) form.append('source', metadata.source);
      return postForm<UploadDocumentResponse>('/api/v1/documents/upload', form, signal);
    },

    /** REQ-05 — List all indexed medical documents */
    listDocuments(signal?: AbortSignal): Promise<PatientDocument[]> {
      return get<Record<string, unknown>[]>('/api/v1/documents', signal).then((docs) =>
        docs.map((d) => ({
          id: d['id'] as string,
          title: (d['title'] as string) || (d['original_name'] as string) || '',
          source: d['source'] as string,
          s3Key: (d['s3_key'] ?? d['s3Key']) as string,
          originalName: (d['original_name'] ?? d['originalName']) as string,
          sizeBytes: (d['size_bytes'] ?? d['sizeBytes'] ?? 0) as number,
          indexedAt: (d['indexed_at'] ?? d['indexedAt']) as string | undefined,
          createdAt: (d['created_at'] ?? d['createdAt']) as string,
          chunkCount: (d['chunk_count'] ?? d['chunkCount'] ?? 0) as number,
        }))
      );
    },

    /** REQ-05 — Delete an indexed document by ID */
    deleteDocument(id: string, signal?: AbortSignal): Promise<void> {
      return del<void>(`/api/v1/documents/${encodeURIComponent(id)}`, signal);
    },
  };

  // ─── Files (/api/v1/files) ──────────────────────────────────────────────────

  const files = {
    /**
     * REQ-07 — Upload a patient clinical file to S3.
     * @param file      - The file to upload (lab result, imaging, PDF, CSV)
     * @param patientId - ID of the patient this file belongs to
     */
    uploadFile(file: File, patientId: string, signal?: AbortSignal): Promise<UploadFileResponse> {
      const form = new FormData();
      form.append('file', file);
      form.append('patient_id', patientId);
      return postForm<UploadFileResponse>('/api/v1/files/upload', form, signal);
    },

    /** REQ-07 — Get a pre-signed S3 URL for a patient file */
    getFileUrl(fileId: string, signal?: AbortSignal): Promise<FileUrlResponse> {
      return get<FileUrlResponse>(`/api/v1/files/${encodeURIComponent(fileId)}`, signal);
    },
  };

  const alerts = {
    /**
     * REQ-09 — Check a prescription for safety alerts (allergies, interactions,
     * contraindications) against a patient profile.
     * Backend expects: ?antibiotic=<name>&patient_id=<id>
     */
    checkAlerts(antibiotic: string, patientId: string, signal?: AbortSignal): Promise<AlertCheckResponse> {
      return get<AlertCheckResponse>(
        `/api/v1/alerts/check?antibiotic=${encodeURIComponent(antibiotic)}&patient_id=${encodeURIComponent(patientId)}`,
        signal,
      );
    },
  };

  return { auth, chat, diagnose, patients, documents, files, alerts };
}

export type ApiClient = ReturnType<typeof createApiClient>;
