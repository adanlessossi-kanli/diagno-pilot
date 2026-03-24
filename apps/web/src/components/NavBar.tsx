'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { useAuth } from '../contexts/AuthContext';
import LanguageSwitcher from './LanguageSwitcher';

interface NavBarProps {
  locale: string;
}

export default function NavBar({ locale }: NavBarProps) {
  const t = useTranslations('nav');
  const { user, logout } = useAuth();

  const base = `/${locale}`;

  return (
    <nav aria-label="Main navigation" className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
      <div className="flex items-center gap-6">
        <Link href={base} className="text-sm font-medium text-gray-700 hover:text-blue-600">
          {t('home')}
        </Link>
        <Link href={`${base}/chat`} className="text-sm font-medium text-gray-700 hover:text-blue-600">
          {t('chat')}
        </Link>
        <Link href={`${base}/diagnose`} className="text-sm font-medium text-gray-700 hover:text-blue-600">
          {t('diagnose')}
        </Link>
        <Link href={`${base}/patients`} className="text-sm font-medium text-gray-700 hover:text-blue-600">
          {t('patients')}
        </Link>
        {user?.role === 'admin' && (
          <Link href={`${base}/admin`} className="text-sm font-medium text-gray-700 hover:text-blue-600">
            {t('admin')}
          </Link>
        )}
      </div>

      <div className="flex items-center gap-4">
        {user && (
          <span className="text-sm text-gray-500">{user.fullName}</span>
        )}
        <LanguageSwitcher />
        <button
          type="button"
          onClick={() => void logout()}
          className="text-sm font-medium text-red-600 hover:text-red-800"
        >
          {t('logout')}
        </button>
      </div>
    </nav>
  );
}
