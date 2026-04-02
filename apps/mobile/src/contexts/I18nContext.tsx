// REQ-7.1, REQ-7.2, REQ-7.4: i18n context for mobile — persists locale via SecureStore (key: diagno_locale)
// Supports fr-TG, fr-BJ, en; uses expo-localization for device locale detection.
import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import * as SecureStore from 'expo-secure-store';
import * as Localization from 'expo-localization';
import type { Locale } from '@diagno-pilot/types';

export const LOCALE_KEY = 'diagno_locale';
export const DEFAULT_LOCALE: Locale = 'fr-TG';
export const SUPPORTED_LOCALES: Locale[] = ['fr-TG', 'fr-BJ', 'en'];

/** Resolve a raw locale string to a supported Locale, falling back to DEFAULT_LOCALE. */
export function resolveLocale(raw: string | null | undefined): Locale {
  if (!raw) return DEFAULT_LOCALE;
  // Exact match
  if ((SUPPORTED_LOCALES as string[]).includes(raw)) return raw as Locale;
  // 'fr' alias → fr-TG (backward compat)
  if (raw === 'fr') return 'fr-TG';
  // Prefix match: e.g. 'fr-TG-x-foo' → 'fr-TG'
  for (const supported of SUPPORTED_LOCALES) {
    if (raw.startsWith(supported)) return supported;
  }
  return DEFAULT_LOCALE;
}

/** Detect the best locale from the device using expo-localization. */
function detectDeviceLocale(): Locale {
  try {
    const locales = Localization.getLocales();
    for (const loc of locales) {
      const resolved = resolveLocale(loc.languageTag);
      if (resolved !== DEFAULT_LOCALE || (SUPPORTED_LOCALES as string[]).includes(loc.languageTag)) {
        return resolved;
      }
    }
  } catch {
    // expo-localization unavailable in test/web environments
  }
  return DEFAULT_LOCALE;
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => Promise<void>;
  /** Increment to signal that cached medical content should be re-fetched. */
  cacheVersion: number;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);
  const [cacheVersion, setCacheVersion] = useState(0);
  const initialised = useRef(false);

  // REQ-7.2: On mount, restore persisted locale or detect from device
  useEffect(() => {
    if (initialised.current) return;
    initialised.current = true;
    (async () => {
      try {
        const stored = await SecureStore.getItemAsync(LOCALE_KEY);
        if (stored) {
          setLocaleState(resolveLocale(stored));
        } else {
          setLocaleState(detectDeviceLocale());
        }
      } catch {
        setLocaleState(detectDeviceLocale());
      }
    })();
  }, []);

  // REQ-7.1, REQ-7.4: Persist locale and invalidate cache so medical content is re-fetched
  const setLocale = useCallback(async (newLocale: Locale) => {
    const safe = resolveLocale(newLocale);
    await SecureStore.setItemAsync(LOCALE_KEY, safe);
    setLocaleState(safe);
    setCacheVersion((v) => v + 1);
  }, []);

  return (
    <I18nContext.Provider value={{ locale, setLocale, cacheVersion }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used within I18nProvider');
  return ctx;
}
