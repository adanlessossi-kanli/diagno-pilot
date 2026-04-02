import { defineRouting } from 'next-intl/routing';
import type { Locale } from '@diagno-pilot/types';

export const routing = defineRouting({
  locales: ['fr-TG', 'fr-BJ', 'en'] as const,
  defaultLocale: 'fr-TG' as const,
  localeDetection: true,
});

/** All supported locale values (Requirements 6.2, 6.6) */
export const SUPPORTED_LOCALES: readonly Locale[] = ['fr-TG', 'fr-BJ', 'en'];

/**
 * Resolves a locale string to a supported locale.
 * - `fr` is treated as an alias for `fr-TG` (Requirement 9.1 backward compat)
 * - Any unsupported locale falls back to `fr-TG` (Requirement 1.3, 6.6)
 */
export function resolveLocale(locale: string | undefined | null): 'fr-TG' | 'fr-BJ' | 'en' {
  if (locale === 'fr') return 'fr-TG';
  if (locale && (SUPPORTED_LOCALES as readonly string[]).includes(locale)) {
    return locale as 'fr-TG' | 'fr-BJ' | 'en';
  }
  return 'fr-TG';
}
