import { getRequestConfig } from 'next-intl/server';
import type { AbstractIntlMessages } from 'next-intl';
import { routing } from './routing';
import { getMessages } from '@diagno-pilot/i18n';

export default getRequestConfig(async ({ requestLocale }) => {
  let locale = await requestLocale;

  // Fallback to default locale if not valid
  if (!locale || !routing.locales.includes(locale as 'fr' | 'en')) {
    locale = routing.defaultLocale;
  }

  const messages = await getMessages(locale as 'fr' | 'en');

  return {
    locale,
    messages: messages as AbstractIntlMessages,
  };
});
