import type { Locale } from '@diagno-pilot/types';

export type { Locale };

export const locales: Locale[] = ['fr', 'en', 'fr-TG', 'fr-BJ'];
export const defaultLocale: Locale = 'fr-TG';

/**
 * Deep-merge two plain objects. Values from `override` take precedence.
 * Arrays are replaced (not concatenated).
 */
function deepMerge(
  base: Record<string, unknown>,
  override: Record<string, unknown>,
): Record<string, unknown> {
  const result: Record<string, unknown> = { ...base };
  for (const key of Object.keys(override)) {
    const baseVal = base[key];
    const overrideVal = override[key];
    if (
      overrideVal !== null &&
      typeof overrideVal === 'object' &&
      !Array.isArray(overrideVal) &&
      baseVal !== null &&
      typeof baseVal === 'object' &&
      !Array.isArray(baseVal)
    ) {
      result[key] = deepMerge(
        baseVal as Record<string, unknown>,
        overrideVal as Record<string, unknown>,
      );
    } else {
      result[key] = overrideVal;
    }
  }
  return result;
}

/**
 * Load translation messages for a given locale.
 * For `fr-TG` and `fr-BJ`, deep-merges the base `fr.json` with the
 * region-specific override file.
 */
export async function getMessages(locale: Locale): Promise<Record<string, unknown>> {
  if (locale === 'fr-TG' || locale === 'fr-BJ') {
    const [base, override] = await Promise.all([
      import('./locales/fr.json'),
      import(`./locales/${locale}.json`),
    ]);
    return deepMerge(base.default as Record<string, unknown>, override.default as Record<string, unknown>);
  }
  const messages = await import(`./locales/${locale}.json`);
  return messages.default;
}

/**
 * Synchronously get messages (for use in non-async contexts).
 * For `fr-TG` and `fr-BJ`, deep-merges the base `fr.json` with the
 * region-specific override file.
 * Falls back to French if locale is not supported.
 */
export function getMessagesSync(locale: Locale): Record<string, unknown> {
  if (locale === 'fr-TG' || locale === 'fr-BJ') {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const base = require('./locales/fr.json') as Record<string, unknown>;
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const override = require(`./locales/${locale}.json`) as Record<string, unknown>;
    return deepMerge(base, override);
  }
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  return require(`./locales/${locale}.json`);
}
