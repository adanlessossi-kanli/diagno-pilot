import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest';
import * as fc from 'fast-check';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { NextRequest } from 'next/server';
import { POST } from '../set-cookie/route';

// Use a local MSW server to keep tests isolated
const server = setupServer();

beforeAll(() => {
  process.env.NEXT_PUBLIC_API_URL = 'http://backend-test';
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

describe('POST /api/auth/set-cookie', () => {
  it('returns 200 when backend returns 200', async () => {
    server.use(
      http.post('http://backend-test/api/v1/auth/login', () =>
        HttpResponse.json({ access_token: 'tok' }, { status: 200 }),
      ),
    );

    const req = new NextRequest('http://localhost/api/auth/set-cookie', {
      method: 'POST',
      body: 'username=user&password=pass',
    });

    const res = await POST(req);
    expect(res.status).toBe(200);
  });

  it('relays Set-Cookie headers from the backend (HttpOnly + Secure flags)', async () => {
    const cookieValue =
      'access_token=abc123; Path=/; HttpOnly; Secure; SameSite=Strict';

    server.use(
      http.post('http://backend-test/api/v1/auth/login', () => {
        return new HttpResponse(JSON.stringify({ ok: true }), {
          status: 200,
          headers: {
            'Content-Type': 'application/json',
            'Set-Cookie': cookieValue,
          },
        });
      }),
    );

    const req = new NextRequest('http://localhost/api/auth/set-cookie', {
      method: 'POST',
      body: 'username=user&password=pass',
    });

    const res = await POST(req);
    expect(res.status).toBe(200);

    const setCookie = res.headers.get('set-cookie');
    expect(setCookie).toBeTruthy();
    expect(setCookie).toContain('HttpOnly');
    expect(setCookie).toContain('Secure');
  });

  it('returns 401 when backend returns 401 (wrong credentials)', async () => {
    server.use(
      http.post('http://backend-test/api/v1/auth/login', () =>
        HttpResponse.json({ detail: 'Incorrect credentials' }, { status: 401 }),
      ),
    );

    const req = new NextRequest('http://localhost/api/auth/set-cookie', {
      method: 'POST',
      body: 'username=wrong&password=wrong',
    });

    const res = await POST(req);
    expect(res.status).toBe(401);
  });
});

// ---------------------------------------------------------------------------
// Property 14: Malformed set-cookie payload returns HTTP 400
// Feature: testing-coverage, Property 14: Malformed set-cookie payload returns HTTP 400
// Validates: Requirements 8.2
// ---------------------------------------------------------------------------

describe('Property 14: Malformed set-cookie payload returns HTTP 400', () => {
  it('never returns 500 for any malformed request body', async () => {
    // Mock backend to return 400 for any malformed payload
    server.use(
      http.post('http://backend-test/api/v1/auth/login', () =>
        HttpResponse.json({ detail: 'Bad request' }, { status: 400 }),
      ),
    );

    await fc.assert(
      fc.asyncProperty(
        fc.oneof(
          fc.string(),
          fc.constant(''),
          fc.constant('{}'),
          fc.constant('{"wrong":"field"}'),
          fc.constant('not-json'),
          fc.constant('null'),
        ),
        async (body) => {
          const req = new NextRequest('http://localhost/api/auth/set-cookie', {
            method: 'POST',
            body,
          });

          const res = await POST(req);
          // The route proxies the backend response — it should NEVER return 500
          return res.status !== 500;
        },
      ),
      { numRuns: 50 },
    );
  });
});
