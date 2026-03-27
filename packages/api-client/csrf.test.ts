// @vitest-environment jsdom
// Unit tests for getCsrfToken helper and CSRF header injection
// Feature: security-hardening, Property 11: CSRF middleware enforces token on all state-mutating endpoints

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as fc from 'fast-check';
import { createApiClient, getCsrfToken } from './index';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function clearCsrfCookie() {
  document.cookie = 'csrf_token=; Max-Age=0; path=/';
}

// ─── getCsrfToken ─────────────────────────────────────────────────────────────

describe('getCsrfToken', () => {
  afterEach(() => {
    clearCsrfCookie();
  });

  it('returns empty string when no csrf_token cookie is set', () => {
    clearCsrfCookie();
    expect(getCsrfToken()).toBe('');
  });

  it('returns the csrf_token value when set', () => {
    document.cookie = 'csrf_token=abc123';
    expect(getCsrfToken()).toBe('abc123');
  });

  it('parses csrf_token correctly when multiple cookies are present', () => {
    document.cookie = 'other=value';
    document.cookie = 'csrf_token=mytoken';
    document.cookie = 'another=thing';
    expect(getCsrfToken()).toBe('mytoken');
  });

  it('decodes URL-encoded csrf_token values', () => {
    document.cookie = 'csrf_token=hello%20world';
    expect(getCsrfToken()).toBe('hello world');
  });

  it('returns empty string after cookie is cleared', () => {
    document.cookie = 'csrf_token=temp';
    clearCsrfCookie();
    expect(getCsrfToken()).toBe('');
  });
});

// ─── CSRF header injection on mutating methods ────────────────────────────────

describe('CSRF header injection on mutating methods', () => {
  beforeEach(() => {
    document.cookie = 'csrf_token=test-csrf-token';
  });

  afterEach(() => {
    clearCsrfCookie();
    vi.unstubAllGlobals();
  });

  const mutatingCalls: Array<{ method: string; call: (c: ReturnType<typeof createApiClient>) => Promise<unknown> }> = [
    { method: 'POST',   call: (c) => c.auth.logout() },
    { method: 'POST',   call: (c) => c.patients.createPatient({ allergies: [], renalFailure: false, hepaticFailure: false, currentMedications: [] }) },
    { method: 'PUT',    call: (c) => c.patients.updatePatient('id', {}) },
    { method: 'DELETE', call: (c) => c.documents.deleteDocument('id') },
  ];

  for (const { method, call } of mutatingCalls) {
    it(`injects X-CSRF-Token on ${method} requests`, async () => {
      // Feature: security-hardening, Property 11: CSRF middleware enforces token on all state-mutating endpoints
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })));
      const c = createApiClient('http://localhost');
      try { await call(c); } catch {}
      const [, init] = vi.mocked(fetch).mock.calls[0];
      expect((init?.headers as Record<string, string>)['X-CSRF-Token']).toBe('test-csrf-token');
    });
  }

  it('does NOT inject X-CSRF-Token on GET requests', async () => {
    // Feature: security-hardening, Property 11: CSRF middleware enforces token on all state-mutating endpoints
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('[]', { status: 200 })));
    const c = createApiClient('http://localhost');
    try { await c.diagnose.listAntibiotics(); } catch {}
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect((init?.headers as Record<string, string>)['X-CSRF-Token']).toBeUndefined();
  });

  it('does NOT inject X-CSRF-Token when csrf_token cookie is absent', async () => {
    clearCsrfCookie();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })));
    const c = createApiClient('http://localhost');
    try { await c.auth.logout(); } catch {}
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect((init?.headers as Record<string, string>)['X-CSRF-Token']).toBeUndefined();
  });
});

// ─── CSRF injection — property-based ─────────────────────────────────────────

describe('CSRF injection — property-based', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    clearCsrfCookie();
  });

  it('X-CSRF-Token matches csrf_token cookie for any token value', async () => {
    // Feature: security-hardening, Property 11: CSRF middleware enforces token on all state-mutating endpoints
    await fc.assert(
      fc.asyncProperty(
        // Cookie values cannot contain semicolons, commas, or whitespace per RFC 6265
        fc.string({ minLength: 1, maxLength: 64 }).map((s) => s.replace(/[;,\s]/g, 'x')).filter((s) => s.length > 0),
        async (tokenValue) => {
          document.cookie = `csrf_token=${encodeURIComponent(tokenValue)}`;
          vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })));
          const c = createApiClient('http://localhost');
          try { await c.auth.logout(); } catch {}
          const [, init] = vi.mocked(fetch).mock.calls[0];
          expect((init?.headers as Record<string, string>)['X-CSRF-Token']).toBe(tokenValue);
          vi.unstubAllGlobals();
          clearCsrfCookie();
        },
      ),
      { numRuns: 50 },
    );
  });
});
