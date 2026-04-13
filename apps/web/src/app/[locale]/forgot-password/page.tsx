'use client';

import Link from 'next/link';
import { useTranslations, useLocale } from 'next-intl';
import DiagnoPilotLogo from '../../../components/DiagnoPilotLogo';

export default function ForgotPasswordPage() {
  const t = useTranslations('auth');
  const locale = useLocale();

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-md p-8 bg-white rounded-xl shadow-md text-center">
        <DiagnoPilotLogo size={40} className="mx-auto mb-2" />
        <span className="text-primary-600 font-bold text-2xl block mb-6">Diagno-Pilot</span>

        <h1 className="text-2xl font-bold mb-4">{t('forgotPasswordTitle')}</h1>

        <p className="text-sm text-gray-600 mb-6">
          {t('forgotPasswordMessage')}
        </p>

        <Link
          href={`/${locale}/login`}
          className="inline-block text-sm font-medium text-primary-600 hover:underline"
        >
          {t('backToLogin')}
        </Link>
      </div>
    </main>
  );
}
