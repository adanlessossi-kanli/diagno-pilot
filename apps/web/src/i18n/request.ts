import { getRequestConfig } from 'next-intl/server';
import type { AbstractIntlMessages } from 'next-intl';
import { routing, resolveLocale } from './routing';
import { getMessages } from '@diagno-pilot/i18n';
import type { Locale } from '@diagno-pilot/types';

export default getRequestConfig(async ({ requestLocale }) => {
  const raw = await requestLocale;
  const locale: Locale = resolveLocale(raw);

  const messages = await getMessages(locale);

  return {
    locale,
    messages: messages as AbstractIntlMessages,
  };
});

// Re-export for convenience
export { routing };
