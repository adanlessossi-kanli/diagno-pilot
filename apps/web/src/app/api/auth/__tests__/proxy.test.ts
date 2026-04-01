import { describe, it, expect, beforeAll, afterEach, afterAll, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { NextRequest } from 'next/server';

// Set env BEFORE the route module is imported so the BACKEND constant is correct
vi.stubEnv('BACKEND_INTERNAL_URL', 'http://backend-internal-test');

// Dynamic import after env is set
const { POST, GET } = await import('../[...path]/route');

// Use a local MSW server to keep tests isolated
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

describe('Auth proxy — status code propagation', () => {
  it('propagates 401 from backend (not 500)', async () => {
    server.use(
      http.post('http://backend-internal-test/api/v1/auth/logout', () =>
        HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }),
      ),
    );

    const req = new NextRequest('http://localhost/api/auth/logout', {
      method: 'POST',
    });

    const res = await POST(req, { params: Promise.resolve({ path: ['logout'] }) });
    expect(res.status).toBe(401);
  });

  it('propagates 403 from backend (not 500)', async () => {
    server.use(
      http.post('http://backend-internal-test/api/v1/auth/logout', () =>
        HttpResponse.json({ detail: 'Forbidden' }, { status: 403 }),
      ),
    );

    const req = new NextRequest('http://localhost/api/auth/logout', {
      method: 'POST',
    });

    const res = await POST(req, { params: Promise.resolve({ path: ['logout'] }) });
    expect(res.status).toBe(403);
  });

  it('relays Set-Cookie headers from backend on 200', async () => {
    const cookieValue = 'session=xyz; Path=/; HttpOnly; Secure; SameSite=Strict';

    server.use(
      http.get('http://backend-internal-test/api/v1/auth/me', () => {
        return new HttpResponse(JSON.stringify({ sub: 'user123' }), {
          status: 200,
          headers: {
            'Content-Type': 'application/json',
            'Set-Cookie': cookieValue,
          },
        });
      }),
    );

    const req = new NextRequest('http://localhost/api/auth/me', {
      method: 'GET',
    });

    const res = await GET(req, { params: Promise.resolve({ path: ['me'] }) });
    expect(res.status).toBe(200);

    const setCookie = res.headers.get('set-cookie');
    expect(setCookie).toBeTruthy();
    expect(setCookie).toContain('HttpOnly');
    expect(setCookie).toContain('Secure');
  });

  it('returns 503 when backend is unreachable', async () => {
    server.use(
      http.post('http://backend-internal-test/api/v1/auth/logout', () =>
        HttpResponse.error(),
      ),
    );

    const req = new NextRequest('http://localhost/api/auth/logout', {
      method: 'POST',
    });

    const res = await POST(req, { params: Promise.resolve({ path: ['logout'] }) });
    expect(res.status).toBe(503);
  });
});
