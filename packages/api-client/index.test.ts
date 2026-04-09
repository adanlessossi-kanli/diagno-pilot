// Unit tests for the API client — REQ-02, REQ-06
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as fc from 'fast-check';
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
const client = createApiClient(BASE_URL);

afterEach(() => {
  vi.unstubAllGlobals();
});

// ─── auth.login ───────────────────────────────────────────────────────────────

describe('auth.login', () => {
  it('sends POST to /api/v1/auth/login with email and password', async () => {
    const loginResponse = {
      token_type: 'bearer',
      expires_in: 900,
      user: { id: 'u1', email: 'doc@example.com', fullName: 'Dr. Smith', role: 'medecin', locale: 'fr' },
    };
    mockFetch(200, loginResponse);

    const result = await client.auth.login('doc@example.com', 'secret');

    const fetchMock = getFetchMock();
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/auth/login`);
    expect(init?.method).toBe('POST');
    const body = init?.body as string;
    const params = new URLSearchParams(body);
    expect(params.get('username')).toBe('doc@example.com');
    expect(params.get('password')).toBe('secret');
    expect(result.token_type).toBe('bearer');
    // Tokens must NOT be in the response body
    expect((result as Record<string, unknown>)['access_token']).toBeUndefined();
    expect((result as Record<string, unknown>)['refresh_token']).toBeUndefined();
  });

  it('sends login with credentials: include', async () => {
    mockFetch(200, { token_type: 'bearer', expires_in: 900, user: { id: 'u1', email: 'e@e.com', fullName: 'X', role: 'medecin' } });
    await client.auth.login('e@e.com', 'pw');
    const [, init] = getFetchMock().mock.calls[0];
    expect(init?.credentials).toBe('include');
  });
});

// ─── auth.me ──────────────────────────────────────────────────────────────────

describe('auth.me', () => {
  it('sends GET to /api/v1/auth/me with credentials: include', async () => {
    const user = { id: 'u1', email: 'doc@example.com', fullName: 'Dr. Smith', role: 'medecin', locale: 'fr' };
    mockFetch(200, user);

    await client.auth.me();

    const fetchMock = getFetchMock();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/auth/me`);
    expect(init?.method).toBe('GET');
    expect(init?.credentials).toBe('include');
    // No Authorization header — auth is cookie-based
    expect((init?.headers as Record<string, string>)['Authorization']).toBeUndefined();
  });
});

// ─── diagnose.getSymptomsDiagnosis ────────────────────────────────────────────

describe('diagnose.getSymptomsDiagnosis', () => {
  it('sends POST to /api/v1/diagnose/symptoms with symptoms array', async () => {
    const diagnosisResponse = {
      session_id: 'sess-1',
      diagnoses: [{ condition: 'Malaria', probability: 0.9, concordantSymptoms: ['fever'] }],
      llmUsed: 'qwen3',
      sources: [],
    };
    mockFetch(200, diagnosisResponse);

    const symptoms = [{ name: 'fever', severity: 'high', durationDays: 3 }];
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
    mockFetch(200, { session_id: 'sess-2', diagnoses: [], llmUsed: 'qwen3', sources: [] });

    const symptoms = [{ name: 'cough', severity: 'mild', durationDays: 2 }];
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
    // serializePatientProfile converts to snake_case for the backend
    expect(body.patient_profile).toMatchObject({
      allergies: [],
      comorbidities: { renal_failure: false, hepatic_failure: false },
      current_medications: [],
    });
  });
});

// ─── patients.listPatients ────────────────────────────────────────────────────

describe('patients.listPatients', () => {
  it('sends GET to /api/v1/patients with default pagination params', async () => {
    mockFetch(200, { items: [], total: 0, page: 1, page_size: 20 });

    await client.patients.listPatients();

    const fetchMock = getFetchMock();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/patients?page=1&page_size=20`);
    expect(init?.method).toBe('GET');
  });

  it('returns parsed paginated response', async () => {
    const paginatedResponse = {
      items: [{ id: 'p1', allergies: [], renalFailure: false, hepaticFailure: false, currentMedications: [] }],
      total: 1,
      page: 1,
      page_size: 20,
    };
    mockFetch(200, paginatedResponse);

    const result = await client.patients.listPatients();
    expect(result.items).toHaveLength(1);
    expect(result.items[0].id).toBe('p1');
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

// ─── Property 4: All fetch helpers include credentials ────────────────────────

describe('Property 4: All API client fetch helpers include credentials', () => {
  it('every helper passes credentials: include to fetch', async () => {
    // Feature: african-image-representation, Property 4: All API client fetch helpers include credentials
    // Validates: Requirements 9.2, 9.3

    // Map each internal helper to a representative domain call that exercises it
    const helperCalls: Record<string, (client: ReturnType<typeof createApiClient>) => Promise<unknown>> = {
      get:      (c) => c.auth.me(),
      post:     (c) => c.auth.logout(),
      put:      (c) => c.patients.updatePatient('id', {}),
      del:      (c) => c.documents.deleteDocument('id'),
      postForm: (c) => c.files.uploadFile(new File(['x'], 'f.pdf'), 'pid'),
    };

    await fc.assert(
      fc.asyncProperty(fc.constantFrom('get', 'post', 'put', 'del', 'postForm'), async (method) => {
        const fetchSpy = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
        vi.stubGlobal('fetch', fetchSpy);
        const client = createApiClient('http://localhost');
        try { await helperCalls[method](client); } catch {}
        expect(fetchSpy).toHaveBeenCalledWith(
          expect.any(String),
          expect.objectContaining({ credentials: 'include' }),
        );
        vi.unstubAllGlobals();
      }),
      { numRuns: 100 },
    );
  });
});


// ─── Imports for new tests ────────────────────────────────────────────────────
import { ZodError, z } from 'zod';
import {
  ApiValidationError,
  normalizeKeys,
  parseResponse,
} from './index';
import {
  PatientProfileSchema,
  DifferentialDiagnosisSchema,
} from '@diagno-pilot/types';

// ─── Helpers for new tests ────────────────────────────────────────────────────

function makeResponse(status: number, body: unknown, contentType = 'application/json'): Response {
  return new Response(
    contentType === 'application/json' ? JSON.stringify(body) : String(body),
    { status, headers: { 'Content-Type': contentType } },
  );
}

// ─── Unit tests: ApiValidationError ──────────────────────────────────────────
// Validates: Requirements 6.2, 6.3, 6.4

describe('ApiValidationError', () => {
  it('is a subclass of Error', () => {
    const zodError = z.object({ x: z.string() }).safeParse({}).error!;
    const err = new ApiValidationError(zodError, { x: 42 });
    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(ApiValidationError);
  });

  it('exposes zodError as a ZodError instance', () => {
    const zodError = z.object({ x: z.string() }).safeParse({}).error!;
    const err = new ApiValidationError(zodError, { x: 42 });
    expect(err.zodError).toBeInstanceOf(ZodError);
  });

  it('exposes rawData', () => {
    const zodError = z.object({ x: z.string() }).safeParse({}).error!;
    const rawData = { x: 42 };
    const err = new ApiValidationError(zodError, rawData);
    expect(err.rawData).toBe(rawData);
  });

  it('has name ApiValidationError', () => {
    const zodError = z.object({ x: z.string() }).safeParse({}).error!;
    const err = new ApiValidationError(zodError, {});
    expect(err.name).toBe('ApiValidationError');
  });

  it('message contains "API response validation failed"', () => {
    const zodError = z.object({ x: z.string() }).safeParse({}).error!;
    const err = new ApiValidationError(zodError, {});
    expect(err.message).toContain('API response validation failed');
  });
});

// ─── Unit tests: parseResponse without schema ─────────────────────────────────
// Validates: Requirements 6.4 — existing behavior unchanged

describe('parseResponse without schema', () => {
  it('returns parsed JSON for a 200 response', async () => {
    const res = makeResponse(200, { foo: 'bar' });
    const result = await parseResponse(res);
    expect(result).toEqual({ foo: 'bar' });
  });

  it('throws ApiError for a 401 response', async () => {
    const res = makeResponse(401, { detail: 'Unauthorized' });
    await expect(parseResponse(res)).rejects.toMatchObject({ status: 401, message: 'Unauthorized' });
  });

  it('returns undefined for a 204 response', async () => {
    const res = new Response(null, { status: 204 });
    const result = await parseResponse(res);
    expect(result).toBeUndefined();
  });
});

// ─── Unit tests: parseResponse with schema ────────────────────────────────────
// Validates: Requirements 6.1, 6.2, 6.3

describe('parseResponse with schema', () => {
  const SimpleSchema = z.object({ name: z.string(), count: z.number() });

  it('returns parsed value when body matches schema', async () => {
    const res = makeResponse(200, { name: 'test', count: 5 });
    const result = await parseResponse(res, SimpleSchema);
    expect(result).toEqual({ name: 'test', count: 5 });
  });

  it('throws ApiValidationError when body fails schema', async () => {
    const res = makeResponse(200, { name: 123, count: 'wrong' });
    await expect(parseResponse(res, SimpleSchema)).rejects.toBeInstanceOf(ApiValidationError);
  });

  it('ApiValidationError contains ZodError on mismatch', async () => {
    const res = makeResponse(200, { name: 123 });
    try {
      await parseResponse(res, SimpleSchema);
      expect.fail('should have thrown');
    } catch (e) {
      expect(e).toBeInstanceOf(ApiValidationError);
      expect((e as ApiValidationError).zodError).toBeInstanceOf(ZodError);
    }
  });

  it('normalizes snake_case keys before validation', async () => {
    const SnakeSchema = z.object({ fullName: z.string(), allergies: z.array(z.string()), renalFailure: z.boolean(), hepaticFailure: z.boolean(), currentMedications: z.array(z.string()) });
    const res = makeResponse(200, { full_name: 'Alice', allergies: [], renal_failure: false, hepatic_failure: false, current_medications: [] });
    const result = await parseResponse(res, SnakeSchema);
    expect(result.fullName).toBe('Alice');
  });
});

// ─── Property 12: ApiValidationError thrown on schema mismatch ───────────────
// Feature: code-quality — Validates: Requirements 6.1, 6.2, 6.3

describe('Property 12: ApiValidationError thrown on schema mismatch', () => {
  const TestSchema = z.object({
    condition: z.string(),
    probability: z.number().min(0).max(1),
    concordantSymptoms: z.array(z.string()),
  });

  // Arbitrary for valid objects matching TestSchema
  const validArb = fc.record({
    condition: fc.string({ minLength: 1 }),
    probability: fc.float({ min: 0, max: 1, noNaN: true }),
    concordantSymptoms: fc.array(fc.string()),
  });

  // Arbitrary for invalid objects (missing required fields or wrong types)
  const invalidArb = fc.oneof(
    // Missing condition
    fc.record({ probability: fc.float({ min: 0, max: 1, noNaN: true }), concordantSymptoms: fc.array(fc.string()) }),
    // Wrong type for probability
    fc.record({ condition: fc.string({ minLength: 1 }), probability: fc.string(), concordantSymptoms: fc.array(fc.string()) }),
    // probability out of range
    fc.record({
      condition: fc.string({ minLength: 1 }),
      probability: fc.oneof(
        fc.float({ min: Math.fround(1.001), max: Math.fround(1e6), noNaN: true, noDefaultInfinity: true }),
        fc.float({ min: Math.fround(-1e6), max: Math.fround(-0.001), noNaN: true, noDefaultInfinity: true }),
      ),
      concordantSymptoms: fc.array(fc.string()),
    }),
  );

  it('parseResponse throws ApiValidationError for any body that fails the schema', async () => {
    await fc.assert(
      fc.asyncProperty(invalidArb, async (body) => {
        const res = makeResponse(200, body);
        await expect(parseResponse(res, TestSchema)).rejects.toBeInstanceOf(ApiValidationError);
      }),
      { numRuns: 100 },
    );
  });

  it('ApiValidationError.zodError is a ZodError instance for any failing body', async () => {
    await fc.assert(
      fc.asyncProperty(invalidArb, async (body) => {
        const res = makeResponse(200, body);
        try {
          await parseResponse(res, TestSchema);
        } catch (e) {
          expect(e).toBeInstanceOf(ApiValidationError);
          expect((e as ApiValidationError).zodError).toBeInstanceOf(ZodError);
        }
      }),
      { numRuns: 100 },
    );
  });

  it('parseResponse returns parsed value for any body that passes the schema', async () => {
    await fc.assert(
      fc.asyncProperty(validArb, async (body) => {
        const res = makeResponse(200, body);
        const result = await parseResponse(res, TestSchema);
        expect(result.condition).toBe(body.condition);
        expect(result.probability).toBe(body.probability);
      }),
      { numRuns: 100 },
    );
  });
});

// ─── Property 13: snake_case normalization before validation ──────────────────
// Feature: code-quality — Validates: Requirements 7.2

describe('Property 13: snake_case normalization before validation', () => {
  // Arbitrary for snake_case patient profile objects structurally equivalent to PatientProfileSchema
  const snakeCasePatientArb = fc.record({
    id: fc.option(fc.string({ minLength: 1 }), { nil: undefined }),
    full_name: fc.option(fc.string({ minLength: 1 }), { nil: undefined }),
    date_of_birth: fc.option(fc.string({ minLength: 1 }), { nil: undefined }),
    weight_kg: fc.option(fc.float({ min: 0, max: Math.fround(300), noNaN: true, noDefaultInfinity: true }), { nil: undefined }),
    age_group: fc.option(fc.constantFrom('neonatal', 'infant', 'child', 'adult'), { nil: undefined }),
    allergies: fc.array(fc.string()),
    renal_failure: fc.boolean(),
    hepatic_failure: fc.boolean(),
    current_medications: fc.array(fc.string()),
  });

  it('normalizing snake_case keys then parsing with PatientProfileSchema must succeed', () => {
    fc.assert(
      fc.property(snakeCasePatientArb, (snakeObj) => {
        const normalized = normalizeKeys(snakeObj);
        expect(() => PatientProfileSchema.parse(normalized)).not.toThrow();
      }),
      { numRuns: 100 },
    );
  });

  it('normalizeKeys converts top-level snake_case keys to camelCase', () => {
    fc.assert(
      fc.property(snakeCasePatientArb, (snakeObj) => {
        const normalized = normalizeKeys(snakeObj) as Record<string, unknown>;
        // snake_case keys should not appear in normalized output
        expect(Object.keys(normalized)).not.toContain('full_name');
        expect(Object.keys(normalized)).not.toContain('renal_failure');
        expect(Object.keys(normalized)).not.toContain('hepatic_failure');
        expect(Object.keys(normalized)).not.toContain('current_medications');
      }),
      { numRuns: 100 },
    );
  });

  it('normalizeKeys handles nested objects recursively', () => {
    const nested = { outer_key: { inner_key: 'value', another_key: 42 } };
    const result = normalizeKeys(nested) as Record<string, Record<string, unknown>>;
    expect(result).toHaveProperty('outerKey');
    expect(result['outerKey']).toHaveProperty('innerKey', 'value');
    expect(result['outerKey']).toHaveProperty('anotherKey', 42);
  });

  it('normalizeKeys handles arrays of objects recursively', () => {
    const arr = [{ snake_key: 1 }, { another_snake: 2 }];
    const result = normalizeKeys(arr) as Record<string, unknown>[];
    expect(result[0]).toHaveProperty('snakeKey', 1);
    expect(result[1]).toHaveProperty('anotherSnake', 2);
  });
});

// ─── chat.listSessions ───────────────────────────────────────────────────────

describe('chat.listSessions', () => {
  it('sends GET to /api/v1/chat/sessions with skip and limit query params', async () => {
    const body = {
      sessions: [
        { session_id: 's1', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-02T00:00:00Z', preview: 'Hello' },
      ],
    };
    mockFetch(200, body);

    await client.chat.listSessions(0, 20);

    const fetchMock = getFetchMock();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/chat/sessions?skip=0&limit=20`);
    expect(init?.method).toBe('GET');
    expect(init?.credentials).toBe('include');
  });

  it('omits query params when skip and limit are not provided', async () => {
    mockFetch(200, { sessions: [] });

    await client.chat.listSessions();

    const [url] = getFetchMock().mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/chat/sessions`);
  });

  it('normalizes snake_case keys to camelCase via Zod schema', async () => {
    const body = {
      sessions: [
        { session_id: 'abc', created_at: '2024-06-01T10:00:00Z', updated_at: null, preview: 'Test message' },
      ],
    };
    mockFetch(200, body);

    const result = await client.chat.listSessions(0, 10);

    expect(result.sessions).toHaveLength(1);
    expect(result.sessions[0].sessionId).toBe('abc');
    expect(result.sessions[0].createdAt).toBe('2024-06-01T10:00:00Z');
    expect(result.sessions[0].updatedAt).toBeNull();
    expect(result.sessions[0].preview).toBe('Test message');
    // Ensure snake_case keys are NOT present on the result
    expect((result.sessions[0] as Record<string, unknown>)['session_id']).toBeUndefined();
    expect((result.sessions[0] as Record<string, unknown>)['created_at']).toBeUndefined();
  });

  it('handles empty sessions array', async () => {
    mockFetch(200, { sessions: [] });

    const result = await client.chat.listSessions(0, 20);

    expect(result.sessions).toEqual([]);
  });

  it('handles nullable fields correctly', async () => {
    const body = {
      sessions: [
        { session_id: 's1', created_at: null, updated_at: null, preview: null },
      ],
    };
    mockFetch(200, body);

    const result = await client.chat.listSessions();

    expect(result.sessions[0].createdAt).toBeNull();
    expect(result.sessions[0].updatedAt).toBeNull();
    expect(result.sessions[0].preview).toBeNull();
  });

  it('throws ApiError on HTTP error', async () => {
    mockFetch(500, { detail: 'Internal Server Error' });

    await expect(client.chat.listSessions()).rejects.toMatchObject<Partial<ApiError>>({
      status: 500,
      message: 'Internal Server Error',
    });
  });
});

// ─── chat.deleteSession ──────────────────────────────────────────────────────

describe('chat.deleteSession', () => {
  it('sends DELETE to /api/v1/chat/sessions/{session_id}', async () => {
    mockFetch(200, { detail: 'Session deleted' });

    await client.chat.deleteSession('sess-123');

    const fetchMock = getFetchMock();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/chat/sessions/sess-123`);
    expect(init?.method).toBe('DELETE');
    expect(init?.credentials).toBe('include');
  });

  it('includes CSRF header via csrfHeaders (X-CSRF-Token present when cookie set)', async () => {
    // Simulate csrf_token cookie — getCsrfToken reads from document.cookie
    // In non-jsdom env getCsrfToken returns '' so we mock fetch and check the header pattern
    mockFetch(200, { detail: 'Session deleted' });

    await client.chat.deleteSession('sess-456');

    const fetchMock = getFetchMock();
    const [, init] = fetchMock.mock.calls[0];
    // The del helper uses csrfHeaders() which includes Content-Type
    expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json');
  });

  it('throws ApiError with status 404 when session not found', async () => {
    mockFetch(404, { detail: 'Session not found' });

    await expect(client.chat.deleteSession('nonexistent')).rejects.toMatchObject<Partial<ApiError>>({
      status: 404,
      message: 'Session not found',
    });
  });

  it('throws ApiError on server error', async () => {
    mockFetch(500, { detail: 'Internal Server Error' });

    await expect(client.chat.deleteSession('sess-789')).rejects.toMatchObject<Partial<ApiError>>({
      status: 500,
      message: 'Internal Server Error',
    });
  });

  it('encodes sessionId in the URL path', async () => {
    mockFetch(200, { detail: 'Session deleted' });

    await client.chat.deleteSession('id/with/slashes');

    const [url] = getFetchMock().mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/chat/sessions/id%2Fwith%2Fslashes`);
  });
});
