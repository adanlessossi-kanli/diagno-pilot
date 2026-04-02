/**
 * Feature: i18n-medical-content
 * Property 13: mobile locale detection falls back to fr-TG for unsupported device locales
 * Validates: Requirements 7.2, 7.5
 *
 * Unit tests for mobile I18nContext:
 * - Locale persistence round-trip via mocked SecureStore (REQ-7.1, REQ-7.4)
 * - Accept-Language injection via apiClient (REQ-7.3)
 */

import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react-native';
import * as fc from 'fast-check';
import {
  I18nProvider,
  useI18n,
  SUPPORTED_LOCALES,
  DEFAULT_LOCALE,
  LOCALE_KEY,
  resolveLocale,
} from '../contexts/I18nContext';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockGetItemAsync = jest.fn();
const mockSetItemAsync = jest.fn();
const mockDeleteItemAsync = jest.fn();

jest.mock('expo-secure-store', () => ({
  getItemAsync: (...args: unknown[]) => mockGetItemAsync(...args),
  setItemAsync: (...args: unknown[]) => mockSetItemAsync(...args),
  deleteItemAsync: (...args: unknown[]) => mockDeleteItemAsync(...args),
}));

// Mock expo-localization — controlled per test
const mockGetLocales = jest.fn();
jest.mock('expo-localization', () => ({
  getLocales: () => mockGetLocales(),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

function wrapper({ children }: { children: React.ReactNode }) {
  return <I18nProvider>{children}</I18nProvider>;
}

beforeEach(() => {
  jest.clearAllMocks();
  mockSetItemAsync.mockResolvedValue(undefined);
  mockDeleteItemAsync.mockResolvedValue(undefined);
  // Default: no device locales
  mockGetLocales.mockReturnValue([]);
});

// ─── Property 13: mobile locale fallback to fr-TG ─────────────────────────────

describe('Property 13 — mobile locale detection falls back to fr-TG for unsupported device locales', () => {
  /**
   * Feature: i18n-medical-content, Property 13: mobile locale detection falls back to fr-TG for unsupported device locales
   * Validates: Requirements 7.2, 7.5
   *
   * For any device locale string not in {"fr-TG", "fr-BJ", "en"},
   * resolveLocale() SHALL return "fr-TG".
   */
  it('P13: resolveLocale returns fr-TG for any unsupported locale string', () => {
    // Feature: i18n-medical-content, Property 13: mobile locale detection falls back to fr-TG for unsupported device locales
    const unsupportedLocaleArb = fc
      .string({ minLength: 0, maxLength: 20 })
      .filter(
        (s) =>
          !SUPPORTED_LOCALES.includes(s as typeof SUPPORTED_LOCALES[number]) &&
          s !== 'fr' &&
          !SUPPORTED_LOCALES.some((sup) => s.startsWith(sup)),
      );

    fc.assert(
      fc.property(unsupportedLocaleArb, (locale) => {
        const result = resolveLocale(locale);
        return result === DEFAULT_LOCALE;
      }),
      { numRuns: 100 },
    );
  });

  it('P13: resolveLocale returns fr-TG for null/undefined/empty', () => {
    expect(resolveLocale(null)).toBe('fr-TG');
    expect(resolveLocale(undefined)).toBe('fr-TG');
    expect(resolveLocale('')).toBe('fr-TG');
  });

  it('P13: resolveLocale always returns a member of SUPPORTED_LOCALES for any input', () => {
    // Feature: i18n-medical-content, Property 13: mobile locale detection falls back to fr-TG for unsupported device locales
    fc.assert(
      fc.property(fc.string({ minLength: 0, maxLength: 30 }), (locale) => {
        const result = resolveLocale(locale);
        return (SUPPORTED_LOCALES as string[]).includes(result);
      }),
      { numRuns: 100 },
    );
  });
});

// ─── Unit tests: I18nContext ───────────────────────────────────────────────────

describe('I18nContext — locale persistence round-trip (REQ-7.1, REQ-7.4)', () => {
  it('a. defaults to fr-TG when SecureStore is empty and no device locale', async () => {
    mockGetItemAsync.mockResolvedValue(null);
    mockGetLocales.mockReturnValue([]);

    const { result } = renderHook(() => useI18n(), { wrapper });

    await waitFor(() => expect(result.current.locale).toBe('fr-TG'));
  });

  it('b. restores persisted locale from SecureStore on mount', async () => {
    mockGetItemAsync.mockResolvedValue('fr-BJ');

    const { result } = renderHook(() => useI18n(), { wrapper });

    await waitFor(() => expect(result.current.locale).toBe('fr-BJ'));
    expect(mockGetItemAsync).toHaveBeenCalledWith(LOCALE_KEY);
  });

  it('c. setLocale persists to SecureStore and updates context', async () => {
    mockGetItemAsync.mockResolvedValue(null);

    const { result } = renderHook(() => useI18n(), { wrapper });
    await waitFor(() => expect(result.current.locale).toBe('fr-TG'));

    await act(async () => {
      await result.current.setLocale('en');
    });

    expect(mockSetItemAsync).toHaveBeenCalledWith(LOCALE_KEY, 'en');
    expect(result.current.locale).toBe('en');
  });

  it('d. setLocale with unsupported value falls back to fr-TG', async () => {
    mockGetItemAsync.mockResolvedValue(null);

    const { result } = renderHook(() => useI18n(), { wrapper });
    await waitFor(() => expect(result.current.locale).toBe('fr-TG'));

    await act(async () => {
      // @ts-expect-error — intentionally passing unsupported value
      await result.current.setLocale('de');
    });

    expect(mockSetItemAsync).toHaveBeenCalledWith(LOCALE_KEY, 'fr-TG');
    expect(result.current.locale).toBe('fr-TG');
  });

  it('e. locale persistence round-trip: set then restore', async () => {
    // First mount: set locale to fr-BJ
    mockGetItemAsync.mockResolvedValue(null);
    const { result: r1, unmount } = renderHook(() => useI18n(), { wrapper });
    await waitFor(() => expect(r1.current.locale).toBe('fr-TG'));

    await act(async () => { await r1.current.setLocale('fr-BJ'); });
    expect(r1.current.locale).toBe('fr-BJ');
    unmount();

    // Second mount: SecureStore returns 'fr-BJ'
    mockGetItemAsync.mockResolvedValue('fr-BJ');
    const { result: r2 } = renderHook(() => useI18n(), { wrapper });
    await waitFor(() => expect(r2.current.locale).toBe('fr-BJ'));
  });

  it('f. setLocale increments cacheVersion to trigger medical content re-fetch (REQ-7.4)', async () => {
    mockGetItemAsync.mockResolvedValue(null);

    const { result } = renderHook(() => useI18n(), { wrapper });
    await waitFor(() => expect(result.current.locale).toBe('fr-TG'));

    const versionBefore = result.current.cacheVersion;

    await act(async () => { await result.current.setLocale('fr-BJ'); });

    expect(result.current.cacheVersion).toBe(versionBefore + 1);
  });

  it('g. detects fr-TG from device locale when SecureStore is empty', async () => {
    mockGetItemAsync.mockResolvedValue(null);
    mockGetLocales.mockReturnValue([{ languageTag: 'fr-TG' }]);

    const { result } = renderHook(() => useI18n(), { wrapper });
    await waitFor(() => expect(result.current.locale).toBe('fr-TG'));
  });

  it('h. detects fr-BJ from device locale when SecureStore is empty', async () => {
    mockGetItemAsync.mockResolvedValue(null);
    mockGetLocales.mockReturnValue([{ languageTag: 'fr-BJ' }]);

    const { result } = renderHook(() => useI18n(), { wrapper });
    await waitFor(() => expect(result.current.locale).toBe('fr-BJ'));
  });

  it('i. fr alias maps to fr-TG', async () => {
    mockGetItemAsync.mockResolvedValue('fr');

    const { result } = renderHook(() => useI18n(), { wrapper });
    await waitFor(() => expect(result.current.locale).toBe('fr-TG'));
  });

  it('j. SecureStore error falls back to device locale detection', async () => {
    mockGetItemAsync.mockRejectedValue(new Error('SecureStore unavailable'));
    mockGetLocales.mockReturnValue([{ languageTag: 'en' }]);

    const { result } = renderHook(() => useI18n(), { wrapper });
    await waitFor(() => expect(result.current.locale).toBe('en'));
  });
});

// ─── Unit tests: resolveLocale ─────────────────────────────────────────────────

describe('resolveLocale — unit tests', () => {
  it('returns fr-TG for exact match', () => expect(resolveLocale('fr-TG')).toBe('fr-TG'));
  it('returns fr-BJ for exact match', () => expect(resolveLocale('fr-BJ')).toBe('fr-BJ'));
  it('returns en for exact match', () => expect(resolveLocale('en')).toBe('en'));
  it('maps fr alias to fr-TG', () => expect(resolveLocale('fr')).toBe('fr-TG'));
  it('maps fr-TG-x-foo prefix to fr-TG', () => expect(resolveLocale('fr-TG-x-foo')).toBe('fr-TG'));
  it('maps fr-BJ-variant prefix to fr-BJ', () => expect(resolveLocale('fr-BJ-variant')).toBe('fr-BJ'));
  it('returns fr-TG for unknown locale', () => expect(resolveLocale('de-DE')).toBe('fr-TG'));
  it('returns fr-TG for null', () => expect(resolveLocale(null)).toBe('fr-TG'));
  it('returns fr-TG for empty string', () => expect(resolveLocale('')).toBe('fr-TG'));
});

// ─── Unit tests: Accept-Language injection (REQ-7.3) ──────────────────────────

// eslint-disable-next-line @typescript-eslint/no-var-requires
const { createApiClient } = require('@diagno-pilot/api-client') as typeof import('@diagno-pilot/api-client');

describe('Accept-Language injection via createApiClient (REQ-7.3)', () => {
  /**
   * Validates: Requirements 7.3
   *
   * The apiClient created with a getLocale getter SHALL include
   * Accept-Language: <locale> on every outbound request.
   */
  it('createApiClient injects Accept-Language header from getLocale getter', async () => {
    let capturedHeaders: Record<string, string> | undefined;
    const mockFetch = jest.fn().mockImplementation((_url: string, init: RequestInit) => {
      capturedHeaders = init.headers as Record<string, string>;
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
    });
    global.fetch = mockFetch as typeof fetch;

    const client = createApiClient('http://localhost:8000', undefined, () => 'fr-BJ');
    try {
      await client.patients.listAllPatients();
    } catch {
      // ignore parse errors — we only care about headers
    }

    expect(capturedHeaders?.['Accept-Language']).toBe('fr-BJ');
  });

  it('P13 (fc): for any supported locale, createApiClient injects it as Accept-Language', async () => {
    // Feature: i18n-medical-content, Property 13: mobile locale detection falls back to fr-TG for unsupported device locales
    await fc.assert(
      fc.asyncProperty(
        fc.constantFrom(...SUPPORTED_LOCALES),
        async (locale) => {
          let capturedHeaders: Record<string, string> | undefined;
          global.fetch = jest.fn().mockImplementation((_url: string, init: RequestInit) => {
            capturedHeaders = init.headers as Record<string, string>;
            return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
          }) as typeof fetch;

          const client = createApiClient('http://localhost:8000', undefined, () => locale);
          try { await client.patients.listAllPatients(); } catch { /* ignore */ }

          return capturedHeaders?.['Accept-Language'] === locale;
        },
      ),
      { numRuns: 100 },
    );
  });
});
