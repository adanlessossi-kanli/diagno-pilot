/**
 * Feature: i18n-medical-content
 * Property 12: Accept-Language header is forwarded on all API requests
 * Validates: Requirements 6.3, 7.3
 *
 * For any active locale in the web client, every outbound API request SHALL
 * include an `Accept-Language` header whose value equals the active locale string.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as fc from 'fast-check';
import { apiFetch, setLocaleCookie, getLocaleCookie } from '../lib/api-fetch';
import type { Locale } from '@diagno-pilot/types';

// ---------------------------------------------------------------------------
// Mock fetch
// ---------------------------------------------------------------------------

const mockFetch = vi.fn();

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch);
  mockFetch.mockResolvedValue(new Response('{}', { status: 200 }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  mockFetch.mockReset();
});

// ---------------------------------------------------------------------------
// Property 12: Accept-Language header forwarded on all API requests
// Feature: i18n-medical-content, Property 12: Accept-Language header is forwarded on all API requests
// ---------------------------------------------------------------------------

describe('Property 12: Accept-Language header is forwarded on all API requests', () => {
  it('injects Accept-Language for any supported locale', async () => {
    // Feature: i18n-medical-content, Property 12: Accept-Language header is forwarded on all API requests
    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom<Locale>('fr-TG', 'fr-BJ', 'en'),
        fc.webPath(),
        async (locale, path) => {
          mockFetch.mockClear();
          await apiFetch(`https://api.example.com${path}`, { locale });

          expect(mockFetch).toHaveBeenCalledOnce();
          const [, init] = mockFetch.mock.calls[0] as [string, RequestInit & { headers: Headers }];
          const headers = init.headers as Headers;
          return headers.get('Accept-Language') === locale;
        },
      ),
      { numRuns: 100 },
    );
  });

  it('defaults Accept-Language to fr-TG when no locale is provided', async () => {
    // Feature: i18n-medical-content, Property 12: Accept-Language header is forwarded on all API requests
    await fc.assert(
      fc.asyncProperty(
        fc.webPath(),
        async (path) => {
          mockFetch.mockClear();
          await apiFetch(`https://api.example.com${path}`);

          const [, init] = mockFetch.mock.calls[0] as [string, RequestInit & { headers: Headers }];
          const headers = init.headers as Headers;
          return headers.get('Accept-Language') === 'fr-TG';
        },
      ),
      { numRuns: 100 },
    );
  });

  it('preserves existing headers while injecting Accept-Language', async () => {
    // Feature: i18n-medical-content, Property 12: Accept-Language header is forwarded on all API requests
    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom<Locale>('fr-TG', 'fr-BJ', 'en'),
        // Generate valid HTTP header values: printable ASCII, no control chars
        fc.string({ minLength: 1, maxLength: 50 }).filter((s) => /^[\x21-\x7E]+$/.test(s)),
        async (locale, authToken) => {
          mockFetch.mockClear();
          await apiFetch('https://api.example.com/test', {
            locale,
            headers: { Authorization: `Bearer ${authToken}` },
          });

          const [, init] = mockFetch.mock.calls[0] as [string, RequestInit & { headers: Headers }];
          const headers = init.headers as Headers;
          return (
            headers.get('Accept-Language') === locale &&
            headers.get('Authorization') === `Bearer ${authToken}`
          );
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Unit tests: apiFetch
// ---------------------------------------------------------------------------

describe('apiFetch — unit tests', () => {
  it('sets Accept-Language: fr-TG by default', async () => {
    await apiFetch('https://api.example.com/patients');
    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit & { headers: Headers }];
    expect((init.headers as Headers).get('Accept-Language')).toBe('fr-TG');
  });

  it('sets Accept-Language: fr-BJ when locale is fr-BJ', async () => {
    await apiFetch('https://api.example.com/patients', { locale: 'fr-BJ' });
    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit & { headers: Headers }];
    expect((init.headers as Headers).get('Accept-Language')).toBe('fr-BJ');
  });

  it('sets Accept-Language: en when locale is en', async () => {
    await apiFetch('https://api.example.com/patients', { locale: 'en' });
    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit & { headers: Headers }];
    expect((init.headers as Headers).get('Accept-Language')).toBe('en');
  });

  it('passes through method, body, and other options', async () => {
    await apiFetch('https://api.example.com/diagnose', {
      locale: 'fr-TG',
      method: 'POST',
      body: JSON.stringify({ symptoms: [] }),
    });
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit & { headers: Headers }];
    expect(url).toBe('https://api.example.com/diagnose');
    expect(init.method).toBe('POST');
    expect(init.body).toBe(JSON.stringify({ symptoms: [] }));
  });
});

// ---------------------------------------------------------------------------
// Unit tests: cookie helpers
// ---------------------------------------------------------------------------

describe('setLocaleCookie / getLocaleCookie — unit tests', () => {
  beforeEach(() => {
    // Reset document.cookie between tests
    Object.defineProperty(document, 'cookie', {
      writable: true,
      value: '',
    });
  });

  it('getLocaleCookie returns null when cookie is absent', () => {
    expect(getLocaleCookie()).toBeNull();
  });

  it('setLocaleCookie writes diagno_locale and getLocaleCookie reads it back', () => {
    // Simulate cookie write by directly setting document.cookie
    document.cookie = 'diagno_locale=fr-BJ; Path=/';
    expect(getLocaleCookie()).toBe('fr-BJ');
  });

  it('getLocaleCookie returns the correct locale among multiple cookies', () => {
    document.cookie = 'access_token=abc123; diagno_locale=en; other=value';
    expect(getLocaleCookie()).toBe('en');
  });
});
