/**
 * Feature: role-based-access-control
 * NavBar RBAC tests — Property 7 + unit tests for admin menu visibility
 */

import fc from 'fast-check';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';
import NavBar from '../NavBar';
import type { UserRole } from '@diagno-pilot/types';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('next/link', () => ({
  default: ({
    href,
    children,
    className,
  }: {
    href: string;
    children: React.ReactNode;
    className?: string;
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

vi.mock('../../i18n/navigation', () => ({
  usePathname: () => '/',
}));

vi.mock('../LanguageSwitcher', () => ({
  default: () => <div data-testid="language-switcher" />,
}));

const mockAuthValue = {
  user: null as null | { id: string; email: string; role: string; fullName: string },
  isLoading: false,
  login: vi.fn(),
  logout: vi.fn(),
  fetchWithRefresh: vi.fn(),
  getToken: vi.fn(),
};

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthValue,
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

const NON_ADMIN_ROLES: UserRole[] = ['medecin', 'infirmière', 'guest'];
const ALL_ROLES: UserRole[] = ['admin', 'medecin', 'infirmière', 'guest'];

function renderNavBar(role: UserRole) {
  mockAuthValue.user = { id: '1', email: 'user@test.com', role, fullName: 'Test User' };
  return render(<NavBar locale="fr" />);
}

beforeEach(() => {
  cleanup();
  mockAuthValue.isLoading = false;
});

// ─── Property 7 : Visibilité du menu admin corrélée au rôle ──────────────────

// Feature: role-based-access-control, Property 7: Visibilité du menu admin corrélée au rôle
describe('NavBar RBAC — Property 7: Visibilité du menu admin corrélée au rôle', () => {
  /**
   * Validates: Requirements 3.1, 3.2
   * For any non-admin role, the NavBar must NOT contain the admin navigation link.
   */
  it('ne contient pas le lien admin pour tout rôle non-admin', () => {
    fc.assert(
      fc.property(fc.constantFrom(...NON_ADMIN_ROLES), (role) => {
        cleanup();
        renderNavBar(role);

        // The admin link renders with the translation key 'admin'
        const adminLinks = screen.queryAllByRole('link', { name: /admin/i });
        const hasAdminLink = adminLinks.some((link) =>
          link.getAttribute('href')?.includes('/admin'),
        );

        cleanup();
        return !hasAdminLink;
      }),
      { numRuns: 100 },
    );
  });

  /**
   * Validates: Requirements 3.1
   * For the admin role, the NavBar MUST contain the admin navigation link.
   */
  it('contient le lien admin pour le rôle admin', () => {
    fc.assert(
      fc.property(fc.constant('admin' as UserRole), (role) => {
        cleanup();
        renderNavBar(role);

        const adminLinks = screen.queryAllByRole('link', { name: /admin/i });
        const hasAdminLink = adminLinks.some((link) =>
          link.getAttribute('href')?.includes('/admin'),
        );

        cleanup();
        return hasAdminLink;
      }),
      { numRuns: 100 },
    );
  });
});

// ─── Unit tests ───────────────────────────────────────────────────────────────

describe('NavBar RBAC — tests unitaires de visibilité du menu admin', () => {
  it('admin voit le lien admin', () => {
    renderNavBar('admin');
    const adminLinks = screen.queryAllByRole('link', { name: /admin/i });
    expect(adminLinks.some((l) => l.getAttribute('href')?.includes('/admin'))).toBe(true);
  });

  it('medecin ne voit pas le lien admin', () => {
    renderNavBar('medecin');
    const adminLinks = screen.queryAllByRole('link', { name: /admin/i });
    expect(adminLinks.some((l) => l.getAttribute('href')?.includes('/admin'))).toBe(false);
  });

  it('infirmière ne voit pas le lien admin', () => {
    renderNavBar('infirmière');
    const adminLinks = screen.queryAllByRole('link', { name: /admin/i });
    expect(adminLinks.some((l) => l.getAttribute('href')?.includes('/admin'))).toBe(false);
  });

  it('guest ne voit pas le lien admin', () => {
    renderNavBar('guest');
    const adminLinks = screen.queryAllByRole('link', { name: /admin/i });
    expect(adminLinks.some((l) => l.getAttribute('href')?.includes('/admin'))).toBe(false);
  });
});
