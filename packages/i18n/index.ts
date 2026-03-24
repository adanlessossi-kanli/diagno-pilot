import type { Locale } from '@diagno-pilot/types';

export type { Locale };

export const locales: Locale[] = ['fr', 'en'];
export const defaultLocale: Locale = 'fr';

/**
 * Load translation messages for a given locale.
 * Returns the JSON object for the requested locale.
 */
export async function getMessages(locale: Locale): Promise<Record<string, unknown>> {
  const messages = await import(`./locales/${locale}.json`);
  return messages.default;
}

/**
 * Synchronously get messages (for use in non-async contexts).
 * Falls back to French if locale is not supported.
 */
export function getMessagesSync(locale: Locale): Record<string, unknown> {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  return require(`./locales/${locale}.json`);
}
