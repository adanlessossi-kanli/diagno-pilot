'use client';

import { useLocale } from 'next-intl';
import { usePathname, useRouter } from '../i18n/navigation';
import { routing } from '../i18n/routing';

const COOKIE_NAME = 'NEXT_LOCALE';
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // 1 year in seconds

export default function LanguageSwitcher() {
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();

  const handleSwitch = (newLocale: string) => {
    // Persist the locale choice via cookie (1 year duration)
    // eslint-disable-next-line react-hooks/immutability
    document.cookie = `${COOKIE_NAME}=${newLocale}; path=/; max-age=${COOKIE_MAX_AGE}; SameSite=Lax`;
    // Update the interface without full page reload via next-intl router
    router.replace(pathname, { locale: newLocale });
  };

  return (
    <div className="flex items-center gap-1" aria-label="Language switcher">
      {routing.locales.map((loc) => (
        <button
          key={loc}
          type="button"
          onClick={() => handleSwitch(loc)}
          aria-label={`Switch to ${loc === 'en' ? 'English' : 'French'}`}
          aria-current={locale === loc ? 'true' : undefined}
          className={`text-sm font-semibold min-w-[44px] min-h-[44px] inline-flex items-center justify-center rounded border transition-colors ${
            locale === loc
              ? 'bg-blue-600 text-white border-blue-600'
              : 'text-gray-500 border-gray-300 hover:text-blue-600 hover:border-blue-400'
          }`}
        >
          {loc.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
