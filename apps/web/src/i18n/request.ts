import { getRequestConfig } from 'next-intl/server';
import { routing } from './routing';

export default getRequestConfig(async ({ requestLocale }) => {
  let locale = await requestLocale;

  // Fallback to default locale if not valid
  if (!locale || !routing.locales.includes(locale as 'fr' | 'en')) {
    locale = routing.defaultLocale;
  }

  // Load translations from packages/i18n
  const messages = (await import(`../../../packages/i18n/locales/${locale}.json`)).default;

  return {
    locale,
    messages,
  };
});
