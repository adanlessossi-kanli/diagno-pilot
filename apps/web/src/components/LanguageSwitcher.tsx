'use client';

import { useLocale } from 'next-intl';
import { usePathname, useRouter } from '../i18n/navigation';
import { routing } from '../i18n/routing';

export default function LanguageSwitcher() {
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();

  const handleSwitch = (newLocale: string) => {
    router.replace(pathname, { locale: newLocale });
  };

  return (
    <div className="flex items-center gap-1" aria-label="Language switcher">
      {routing.locales.map((loc) => (
        <button
          key={loc}
          type="button"
          onClick={() => handleSwitch(loc)}
          aria-label={`Switch to ${loc === 'fr' ? 'French' : 'English'}`}
          aria-current={locale === loc ? 'true' : undefined}
          className={`text-xs font-semibold px-2 py-1 rounded transition-colors ${
            locale === loc
              ? 'bg-blue-600 text-white'
              : 'text-gray-500 hover:text-blue-600'
          }`}
        >
          {loc.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
