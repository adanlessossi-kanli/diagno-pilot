'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { useAuth } from '../contexts/AuthContext';
import { usePathname } from '../i18n/navigation';
import type { UserRole } from '@diagno-pilot/types';
import LanguageSwitcher from './LanguageSwitcher';
import DiagnoPilotLogo from './DiagnoPilotLogo';

interface NavBarProps {
  locale: string;
}

interface NavLink {
  href: string;
  label: string;
  path: string;
}

const ROLE_NAV_LINKS: Record<string, Array<{ path: string; labelKey: string }>> = {
  guest: [
    { path: '/login', labelKey: 'signin' },
  ],
  infirmière: [
    { path: '/chat', labelKey: 'chat' },
    { path: '/diagnose', labelKey: 'diagnose' },
    { path: '/patients', labelKey: 'patients' },
  ],
  medecin: [
    { path: '/chat', labelKey: 'chat' },
    { path: '/diagnose', labelKey: 'diagnose' },
    { path: '/patients', labelKey: 'patients' },
    { path: '/documents', labelKey: 'documents' },
  ],
  admin: [
    { path: '/chat', labelKey: 'chat' },
    { path: '/diagnose', labelKey: 'diagnose' },
    { path: '/patients', labelKey: 'patients' },
    { path: '/documents', labelKey: 'documents' },
    { path: '/admin', labelKey: 'adminPanel' },
  ],
};

export default function NavBar({ locale }: NavBarProps) {
  const t = useTranslations('nav');
  const { user, isLoading, logout } = useAuth();
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);

  if (isLoading) return null;

  const base = `/${locale}`;
  const role = user?.role ?? 'guest';
  const roleLinks = ROLE_NAV_LINKS[role] ?? ROLE_NAV_LINKS['guest'];

  const links: NavLink[] = roleLinks.map(({ path, labelKey }) => ({
    href: `${base}${path}`,
    label: t(labelKey as Parameters<typeof t>[0]),
    path,
  }));

  function linkClass(path: string) {
    const isActive = path === '/' ? pathname === '/' : pathname.startsWith(path);
    return isActive
      ? 'text-sm font-semibold text-blue-700 border-b-2 border-blue-700 transition-colors duration-150'
      : 'text-sm font-medium text-gray-700 hover:text-blue-600 transition-colors duration-150';
  }

  return (
    <nav aria-label="Main navigation" className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between relative">
      {/* Wordmark */}
      <Link href={base} className="flex items-center gap-2 text-base font-bold text-primary-600 tracking-tight select-none">
        <DiagnoPilotLogo size={28} />
        <span>Diagno-Pilot</span>
      </Link>

      {/* Desktop links */}
      <div className="hidden md:flex items-center gap-6">
        {links.map((link) => (
          <Link key={link.path} href={link.href} className={linkClass(link.path)}>
            {link.label}
          </Link>
        ))}
      </div>

      {/* Mobile hamburger button */}
      <button
        type="button"
        className="md:hidden text-gray-700"
        aria-label="Open menu"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(true)}
      >
        {/* Hamburger icon — three horizontal lines */}
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>

      {/* Right side */}
      <div className="flex items-center gap-4">
        {user && (
          <>
            <span className="text-sm text-gray-500">{user.fullName} · {user.role}</span>
            <LanguageSwitcher />
            <button
              type="button"
              onClick={() => void logout()}
              className="text-sm font-medium text-red-600 hover:text-red-800 transition-colors duration-150"
            >
              {t('logout')}
            </button>
          </>
        )}
        {!user && <LanguageSwitcher />}
      </div>

      {/* Mobile drawer overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/40 md:hidden"
          onClick={() => setIsOpen(false)}
          aria-hidden="true"
        />
      )}
      {/* Mobile drawer */}
      {isOpen && (
        <div className="drawer-slide-in fixed top-0 left-0 z-50 h-full w-64 bg-white shadow-xl flex flex-col md:hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <span className="font-semibold text-gray-800">Menu</span>
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setIsOpen(false)}
              className="text-gray-500 hover:text-gray-800 transition-colors duration-150"
            >
              {/* Close icon — X */}
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
          <div className="flex flex-col gap-1 p-4">
            {links.map((link) => (
              <Link
                key={link.path}
                href={link.href}
                onClick={() => setIsOpen(false)}
                className={`block px-3 py-2 rounded ${linkClass(link.path)}`}
              >
                {link.label}
              </Link>
            ))}
            <div className="mt-4 pt-4 border-t flex items-center justify-between">
              <LanguageSwitcher />
              {user && (
                <button
                  type="button"
                  onClick={() => void logout()}
                  className="text-sm font-medium text-red-600 hover:text-red-800 transition-colors duration-150"
                >
                  {t('logout')}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
