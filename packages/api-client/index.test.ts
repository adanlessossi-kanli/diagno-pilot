// Unit tests for the API client — REQ-02, REQ-06
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createApiClient } from './index';
import type { ApiError } from './index';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function mockFetch(status: number, body: unknown, contentType = 'application/json') {
  const response = new Response(
    contentType === 'application/json' ? JSON.stringify(body) : String(body),
    {
      status,
      headers: { 'Content-Type': contentType },
    },
  );
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
}

function getFetchMock() {
  return vi.mocked(fetch);
}

// ─── Setup ────────────────────────────────────────────────────────────────────

const BASE_URL = 'http://localhost:8000';
let token: string | null = null;
const client = createApiClient(BASE_URL, () => token);

beforeEach(() => {
  token = null;
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ─── auth.login ───────────────────────────────────────────────────────────────

describe('auth.login', () => {
  it('sends POST to /api/v1/auth/login with email and password', async () => {
    const loginResponse = {
      access_token: 'tok123',
      token_type: 'bearer',
      user: { id: 'u1', email: 'doc@example.com', fullName: 'Dr. Smith', role: 'medecin', locale: 'fr' },
    };
    mockFetch(200, loginResponse);

    const result = await client.auth.login('doc@example.com', 'secret');

    const fetchMock = getFetchMock();
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/auth/login`);
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({ email: 'doc@example.com', password: 'secret' });
    expect(result.access_token).toBe('tok123');
  });
});

// ─── auth.me ──────────────────────────────────────────────────────────────────

describe('auth.me', () => {
  it('sends GET with Authorization header when token is set', async () => {
    token = 'my-jwt-token';
    const user = { id: 'u1', email: 'doc@example.com', fullName: 'Dr. Smith', role: 'medecin', locale: 'fr' };
    mockFetch(200, user);

    await client.auth.me();

    const fetchMock = getFetchMock();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/auth/me`);
    expect(init?.method).toBe('GET');
    expect((init?.headers as Record<string, string>)['Authorization']).toBe('Bearer my-jwt-token');
  });

  it('sends GET without Authorization header when no token', async () => {
    token = null;
    const user = { id: 'u1', email: 'doc@example.com', fullName: 'Dr. Smith', role: 'medecin', locale: 'fr' };
    mockFetch(200, user);

    await client.auth.me();

    const fetchMock = getFetchMock();
    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Record<string, string>)['Authorization']).toBeUndefined();
  });
});

// ─── diagnose.getSymptomsDiagnosis ────────────────────────────────────────────

describe('diagnose.getSymptomsDiagnosis', () => {
  it('sends POST to /api/v1/diagnose/symptoms with symptoms array', async () => {
    const diagnosisResponse = {
      diagnoses: [{ condition: 'Malaria', probability: 0.9, concordant_symptoms: ['fever'] }],
      llmUsed: 'qwen3',
      sources: [],
    };
    mockFetch(200, diagnosisResponse);

    const symptoms = [{ name: 'fever', severity: 'high', duration_days: 3 }];
    const result = await client.diagnose.getSymptomsDiagnosis(symptoms);

    const fetchMock = getFetchMock();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/diagnose/symptoms`);
    expect(init?.method).toBe('POST');
    const body = JSON.parse(init?.body as string);
    expect(body.symptoms).toEqual(symptoms);
    expect(body.patient_profile).toBeNull();
    expect(result.diagnoses).toHaveLength(1);
  });

  it('includes patient_profile when provided', async () => {
    mockFetch(200, { diagnoses: [], llmUsed: 'qwen3', sources: [] });

    const symptoms = [{ name: 'cough', severity: 'mild', duration_days: 2 }];
    const profile = {
      allergies: [],
      renalFailure: false,
      hepaticFailure: false,
      currentMedications: [],
    };
    await client.diagnose.getSymptomsDiagnosis(symptoms, profile);

    const fetchMock = getFetchMock();
    const [, init] = fetchMock.mock.calls[0];
    const body = JSON.parse(init?.body as string);
    expect(body.patient_profile).toEqual(profile);
  });
});

// ─── patients.listPatients ────────────────────────────────────────────────────

describe('patients.listPatients', () => {
  it('sends GET to /api/v1/patients', async () => {
    mockFetch(200, []);

    await client.patients.listPatients();

    const fetchMock = getFetchMock();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/patients`);
    expect(init?.method).toBe('GET');
  });

  it('returns parsed patient array', async () => {
    const patients = [
      { id: 'p1', allergies: [], renalFailure: false, hepaticFailure: false, currentMedications: [] },
    ];
    mockFetch(200, patients);

    const result = await client.patients.listPatients();
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('p1');
  });
});

// ─── patients.createPatient ───────────────────────────────────────────────────

describe('patients.createPatient', () => {
  it('sends POST to /api/v1/patients with patient data', async () => {
    const newPatient = {
      id: 'p2',
      fullName: 'Kofi Mensah',
      allergies: ['penicillin'],
      renalFailure: false,
      hepaticFailure: false,
      currentMedications: [],
    };
    mockFetch(200, newPatient);

    const data = {
      fullName: 'Kofi Mensah',
      allergies: ['penicillin'],
      renalFailure: false,
      hepaticFailure: false,
      currentMedications: [],
    };
    const result = await client.patients.createPatient(data);

    const fetchMock = getFetchMock();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/patients`);
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual(data);
    expect(result.id).toBe('p2');
  });
});

// ─── Error handling ───────────────────────────────────────────────────────────

describe('error handling', () => {
  it('throws ApiError with correct status and message on 401', async () => {
    mockFetch(401, { detail: 'Unauthorized' });

    await expect(client.auth.me()).rejects.toMatchObject<Partial<ApiError>>({
      status: 401,
      message: 'Unauthorized',
    });
  });

  it('throws ApiError with correct status on 404', async () => {
    mockFetch(404, { detail: 'Patient not found' });

    await expect(client.patients.getPatient('nonexistent')).rejects.toMatchObject<Partial<ApiError>>({
      status: 404,
      message: 'Patient not found',
    });
  });

  it('throws ApiError with statusText when no detail field', async () => {
    const response = new Response('Internal Server Error', {
      status: 500,
      statusText: 'Internal Server Error',
      headers: { 'Content-Type': 'text/plain' },
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));

    await expect(client.auth.me()).rejects.toMatchObject<Partial<ApiError>>({
      status: 500,
    });
  });
});

// ─── files.uploadFile ─────────────────────────────────────────────────────────

describe('files.uploadFile', () => {
  it('sends FormData without Content-Type header override', async () => {
    const uploadResponse = {
      fileId: 'f1',
      file: {
        id: 'f1',
        patientId: 'p1',
        fileType: 'pdf',
        originalName: 'lab.pdf',
        sizeBytes: 1024,
        createdAt: '2024-01-01T00:00:00Z',
      },
    };
    mockFetch(200, uploadResponse);

    const file = new File(['content'], 'lab.pdf', { type: 'application/pdf' });
    await client.files.uploadFile(file, 'p1');

    const fetchMock = getFetchMock();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/files/upload`);
    expect(init?.method).toBe('POST');
    expect(init?.body).toBeInstanceOf(FormData);
    // Content-Type must NOT be set manually (browser sets it with boundary)
    const headers = init?.headers as Record<string, string> | undefined;
    expect(headers?.['Content-Type']).toBeUndefined();
  });

  it('includes file and patient_id in FormData', async () => {
    mockFetch(200, {
      fileId: 'f2',
      file: { id: 'f2', patientId: 'p2', fileType: 'pdf', originalName: 'result.pdf', sizeBytes: 512, createdAt: '2024-01-01T00:00:00Z' },
    });

    const file = new File(['data'], 'result.pdf', { type: 'application/pdf' });
    await client.files.uploadFile(file, 'p2');

    const fetchMock = getFetchMock();
    const [, init] = fetchMock.mock.calls[0];
    const formData = init?.body as FormData;
    expect(formData.get('patient_id')).toBe('p2');
    expect(formData.get('file')).toBe(file);
  });
});
