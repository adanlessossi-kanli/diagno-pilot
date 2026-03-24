// HTTP API client for Diagno-Pilot
// Covers all backend endpoints: /auth, /chat, /diagnose, /patients, /documents, /files, /alerts
// REQ-01 through REQ-09

import type {
  PatientProfile,
  Consultation,
  ChatMessage,
  ChatSession,
  Symptom,
  DifferentialDiagnosis,
  Prescription,
  SafetyAlert,
  DocumentSource,
} from '@diagno-pilot/types';

// ─── Response types ───────────────────────────────────────────────────────────

export interface AuthUser {
  id: string;
  email: string;
  fullName: string;
  role: string;
  locale: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface DiagnosisResponse {
  diagnoses: DifferentialDiagnosis[];
  llmUsed: string;
  sources: DocumentSource[];
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

export interface ApiError {
  status: number;
  message: string;
  detail?: unknown;
}

// ─── Internal helpers ─────────────────────────────────────────────────────────

async function parseResponse<T>(res: Response): Promise<T> {
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

  return res.json() as Promise<T>;
}

// ─── Factory ──────────────────────────────────────────────────────────────────

/**
 * Creates a typed API client bound to a base URL and an optional token provider.
 *
 * @param baseUrl   - Root URL of the FastAPI backend, e.g. "http://localhost:8000"
 * @param getToken  - Callback that returns the current JWT access token (or null)
 */
export function createApiClient(baseUrl: string, getToken: () => string | null) {
  const base = baseUrl.replace(/\/$/, '');

  function headers(extra?: Record<string, string>): Record<string, string> {
    const token = getToken();
    return {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...extra,
    };
  }

  function get<T>(path: string): Promise<T> {
    return fetch(`${base}${path}`, { method: 'GET', headers: headers() }).then(parseResponse<T>);
  }

  function post<T>(path: string, body?: unknown): Promise<T> {
    return fetch(`${base}${path}`, {
      method: 'POST',
      headers: headers(),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }).then(parseResponse<T>);
  }

  function put<T>(path: string, body?: unknown): Promise<T> {
    return fetch(`${base}${path}`, {
      method: 'PUT',
      headers: headers(),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }).then(parseResponse<T>);
  }

  function del<T>(path: string): Promise<T> {
    return fetch(`${base}${path}`, { method: 'DELETE', headers: headers() }).then(parseResponse<T>);
  }

  function postForm<T>(path: string, formData: FormData): Promise<T> {
    const token = getToken();
    return fetch(`${base}${path}`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    }).then(parseResponse<T>);
  }

  // ─── Auth (/api/v1/auth) ────────────────────────────────────────────────────

  const auth = {
    /** REQ-01 — Authenticate and receive a JWT token */
    login(email: string, password: string): Promise<LoginResponse> {
      return post<LoginResponse>('/api/v1/auth/login', { email, password });
    },

    /** REQ-01 — Invalidate the current session */
    logout(): Promise<void> {
      return post<void>('/api/v1/auth/logout');
    },

    /** REQ-01 — Retrieve the currently authenticated user */
    me(): Promise<AuthUser> {
      return get<AuthUser>('/api/v1/auth/me');
    },
  };

  // ─── Chat (/api/v1/chat) ────────────────────────────────────────────────────

  const chat = {
    /** REQ-04 — Send a message in a chat session */
    sendMessage(
      sessionId: string,
      content: string,
      patientContext?: PatientProfile,
    ): Promise<ChatMessage> {
      return post<ChatMessage>('/api/v1/chat/message', {
        session_id: sessionId,
        content,
        patient_context: patientContext ?? null,
      });
    },

    /** REQ-04 — Retrieve the full message history for a session */
    getHistory(sessionId: string): Promise<ChatSession> {
      return get<ChatSession>(`/api/v1/chat/history/${encodeURIComponent(sessionId)}`);
    },
  };

  // ─── Diagnose (/api/v1/diagnose) ────────────────────────────────────────────

  const diagnose = {
    /** REQ-02 — Submit symptoms and receive differential diagnoses */
    getSymptomsDiagnosis(
      symptoms: Symptom[],
      patientProfile?: PatientProfile,
    ): Promise<DiagnosisResponse> {
      return post<DiagnosisResponse>('/api/v1/diagnose/symptoms', {
        symptoms,
        patient_profile: patientProfile ?? null,
      });
    },

    /** REQ-03 — Request an antibiotic prescription for a given diagnosis */
    getPrescription(
      diagnosisId: string,
      patientProfile: PatientProfile,
    ): Promise<PrescriptionResponse> {
      return post<PrescriptionResponse>('/api/v1/diagnose/prescription', {
        diagnosis_id: diagnosisId,
        patient_profile: patientProfile,
      });
    },

    /** REQ-02, REQ-03 — Retrieve a full diagnose session by ID */
    getSession(sessionId: string): Promise<DiagnoseSession> {
      return get<DiagnoseSession>(`/api/v1/diagnose/session/${encodeURIComponent(sessionId)}`);
    },
  };

  // ─── Patients (/api/v1/patients) ────────────────────────────────────────────

  const patients = {
    /** REQ-06 — List all patients accessible to the current user */
    listPatients(): Promise<PatientProfile[]> {
      return get<PatientProfile[]>('/api/v1/patients');
    },

    /** REQ-06 — Create a new patient record */
    createPatient(data: Omit<PatientProfile, 'id'>): Promise<PatientProfile> {
      return post<PatientProfile>('/api/v1/patients', data);
    },

    /** REQ-06 — Retrieve a single patient by ID */
    getPatient(id: string): Promise<PatientProfile> {
      return get<PatientProfile>(`/api/v1/patients/${encodeURIComponent(id)}`);
    },

    /** REQ-06 — Update an existing patient record */
    updatePatient(id: string, data: Partial<PatientProfile>): Promise<PatientProfile> {
      return put<PatientProfile>(`/api/v1/patients/${encodeURIComponent(id)}`, data);
    },

    /** REQ-07 — List all consultations for a patient */
    listConsultations(patientId: string): Promise<Consultation[]> {
      return get<Consultation[]>(`/api/v1/patients/${encodeURIComponent(patientId)}/consultations`);
    },

    /** REQ-07 — Create a new consultation linked to a patient */
    createConsultation(
      patientId: string,
      data: Omit<Consultation, 'id' | 'createdAt'>,
    ): Promise<Consultation> {
      return post<Consultation>(
        `/api/v1/patients/${encodeURIComponent(patientId)}/consultations`,
        data,
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
    ): Promise<UploadDocumentResponse> {
      const form = new FormData();
      form.append('file', file);
      if (metadata?.title) form.append('title', metadata.title);
      if (metadata?.source) form.append('source', metadata.source);
      return postForm<UploadDocumentResponse>('/api/v1/documents/upload', form);
    },

    /** REQ-05 — List all indexed medical documents */
    listDocuments(): Promise<PatientDocument[]> {
      return get<PatientDocument[]>('/api/v1/documents');
    },

    /** REQ-05 — Delete an indexed document by ID */
    deleteDocument(id: string): Promise<void> {
      return del<void>(`/api/v1/documents/${encodeURIComponent(id)}`);
    },
  };

  // ─── Files (/api/v1/files) ──────────────────────────────────────────────────

  const files = {
    /**
     * REQ-07 — Upload a patient clinical file to S3.
     * @param file      - The file to upload (lab result, imaging, PDF, CSV)
     * @param patientId - ID of the patient this file belongs to
     */
    uploadFile(file: File, patientId: string): Promise<UploadFileResponse> {
      const form = new FormData();
      form.append('file', file);
      form.append('patient_id', patientId);
      return postForm<UploadFileResponse>('/api/v1/files/upload', form);
    },

    /** REQ-07 — Get a pre-signed S3 URL for a patient file */
    getFileUrl(fileId: string): Promise<FileUrlResponse> {
      return get<FileUrlResponse>(`/api/v1/files/${encodeURIComponent(fileId)}`);
    },
  };

  // ─── Alerts (/api/v1/alerts) ────────────────────────────────────────────────

  const alerts = {
    /**
     * REQ-09 — Check a prescription for safety alerts (allergies, interactions,
     * contraindications) against a patient profile.
     */
    checkAlerts(prescriptionId: string, patientId: string): Promise<AlertCheckResponse> {
      return get<AlertCheckResponse>(
        `/api/v1/alerts/check?prescription_id=${encodeURIComponent(prescriptionId)}&patient_id=${encodeURIComponent(patientId)}`,
      );
    },
  };

  return { auth, chat, diagnose, patients, documents, files, alerts };
}

export type ApiClient = ReturnType<typeof createApiClient>;
