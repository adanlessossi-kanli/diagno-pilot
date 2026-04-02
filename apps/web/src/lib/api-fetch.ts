/**
 * Shared API fetch wrapper that injects the `Accept-Language` header on every
 * outbound request to the backend (Requirements 6.3, 9.1).
 *
 * Usage:
 *   import { apiFetch } from '@/lib/api-fetch';
 *   const data = await apiFetch('/api/v1/patients', { locale: 'fr-TG' });
 */

import type { Locale } from '@diagno-pilot/types';

export interface ApiFetchOptions extends RequestInit {
  /** The active locale — injected as `Accept-Language` header. */
  locale?: Locale | string;
}

/**
 * Wraps `fetch` and injects `Accept-Language: <locale>` on every request.
 * Falls back to `fr-TG` when no locale is provided.
 */
export async function apiFetch(url: string, options: ApiFetchOptions = {}): Promise<Response> {
  const { locale = 'fr-TG', headers: existingHeaders, ...rest } = options;

  const headers = new Headers(existingHeaders as HeadersInit | undefined);
  headers.set('Accept-Language', locale);

  return fetch(url, { ...rest, headers });
}

/**
 * Persist the user's locale preference in the `diagno_locale` cookie.
 * The middleware reads this cookie to override browser locale detection
 * (Requirements 6.4, 6.5).
 */
export function setLocaleCookie(locale: Locale): void {
  // Max-age: 1 year; SameSite=Lax; Secure in production
  const maxAge = 60 * 60 * 24 * 365;
  const secure = typeof window !== 'undefined' && window.location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `diagno_locale=${locale}; Max-Age=${maxAge}; Path=/; SameSite=Lax${secure}`;
}

/**
 * Read the `diagno_locale` cookie value from the browser.
 * Returns `null` when the cookie is absent or not in a browser context.
 */
export function getLocaleCookie(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(/(?:^|;\s*)diagno_locale=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}
