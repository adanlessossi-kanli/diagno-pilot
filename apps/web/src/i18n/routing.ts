import { defineRouting } from 'next-intl/routing';

export const routing = defineRouting({
  locales: ['fr', 'en'],
  defaultLocale: 'fr',
  localeDetection: true,
});

/**
 * Resolves a locale string to a supported locale, falling back to 'fr' for
 * any unsupported locale (Requirement 2.7).
 */
export function resolveLocale(locale: string | undefined | null): 'fr' | 'en' {
  if (locale && (routing.locales as readonly string[]).includes(locale)) {
    return locale as 'fr' | 'en';
  }
  return routing.defaultLocale;
}
