'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { useAuth } from '../contexts/AuthContext';
import { usePathname } from '../i18n/navigation';
import LanguageSwitcher from './LanguageSwitcher';

interface NavBarProps {
  locale: string;
}

interface NavLink {
  href: string;
  label: string;
  path: string;
}

export default function NavBar({ locale }: NavBarProps) {
  const t = useTranslations('nav');
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);

  const base = `/${locale}`;

  const links: NavLink[] = [
    { href: base, label: t('home'), path: '/' },
    { href: `${base}/chat`, label: t('chat'), path: '/chat' },
    { href: `${base}/diagnose`, label: t('diagnose'), path: '/diagnose' },
    { href: `${base}/patients`, label: t('patients'), path: '/patients' },
    ...(user?.role === 'admin'
      ? [{ href: `${base}/admin`, label: t('admin'), path: '/admin' }]
      : []),
  ];

  function linkClass(path: string) {
    const isActive = path === '/' ? pathname === '/' : pathname.startsWith(path);
    return isActive
      ? 'text-sm font-semibold text-blue-700 border-b-2 border-blue-700'
      : 'text-sm font-medium text-gray-700 hover:text-blue-600';
  }

  return (
    <nav aria-label="Main navigation" className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between relative">
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
        className="md:hidden text-gray-700 text-xl leading-none"
        aria-label="Open menu"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(true)}
      >
        ☰
      </button>

      {/* Right side */}
      <div className="flex items-center gap-4">
        {user && (
          <span className="text-sm text-gray-500">{user.fullName} · {user.role}</span>
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
        <div className="fixed top-0 left-0 z-50 h-full w-64 bg-white shadow-xl flex flex-col md:hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <span className="font-semibold text-gray-800">Menu</span>
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setIsOpen(false)}
              className="text-gray-500 hover:text-gray-800 text-xl leading-none"
            >
              ✕
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
          </div>
        </div>
      )}
    </nav>
  );
}
