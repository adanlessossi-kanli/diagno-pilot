// REQ-2.2, REQ-2.4, REQ-2.6: i18n context for mobile — persists locale via SecureStore (key: diagno_locale)
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import * as SecureStore from 'expo-secure-store';
import type { Locale } from '@diagno-pilot/types';

export const LOCALE_KEY = 'diagno_locale';
export const DEFAULT_LOCALE: Locale = 'fr';
export const SUPPORTED_LOCALES: Locale[] = ['fr', 'en'];

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => Promise<void>;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);

  // REQ-2.6: Restore persisted locale on mount, default to 'fr'
  useEffect(() => {
    (async () => {
      try {
        const stored = await SecureStore.getItemAsync(LOCALE_KEY);
        if (stored === 'fr' || stored === 'en') {
          setLocaleState(stored);
        }
      } catch {
        // fallback to default
      }
    })();
  }, []);

  // REQ-2.4: Persist locale and update context
  const setLocale = useCallback(async (newLocale: Locale) => {
    const safe: Locale = SUPPORTED_LOCALES.includes(newLocale) ? newLocale : DEFAULT_LOCALE;
    await SecureStore.setItemAsync(LOCALE_KEY, safe);
    setLocaleState(safe);
  }, []);

  return (
    <I18nContext.Provider value={{ locale, setLocale }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used within I18nProvider');
  return ctx;
}
