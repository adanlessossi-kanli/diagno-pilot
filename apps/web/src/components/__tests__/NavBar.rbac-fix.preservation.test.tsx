/**
 * Preservation property tests — RBAC Fix bugfix spec (frontend)
 *
 * These tests verify that EXISTING correct behaviors are NOT broken by the fix.
 * They MUST PASS on the UNFIXED (current) code.
 *
 * **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9**
 *
 * Preserved behaviors confirmed by this file:
 *   - NavBar with role='admin' shows Chat, Diagnostic, Patients, Documents, Admin links
 *   - NavBar with role='medecin' shows Chat, Diagnostic, Patients, Documents (no Admin)
 *   - NavBar with any authenticated role does NOT show Admin link for non-admin
 *   - NavBar returns null for unauthenticated users (current behavior — preserved)
 *
 * Property 6: Preservation — Comportements non affectés par le correctif
 * **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9**
 */

import fc from 'fast-check';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';
import NavBar from '../NavBar';

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

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useParams: () => ({ locale: 'fr' }),
}));

const mockAuthValue = {
  user: null as null | { id: string; email: string; role: string; fullName: string },
  isLoading: false,
  login: vi.fn(),
  logout: vi.fn(),
  fetchWithRefresh: vi.fn(),
};

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthValue,
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

function renderNavBarWithRole(role: string, locale: string = 'fr') {
  mockAuthValue.user = { id: '1', email: 'user@test.com', role, fullName: 'Test User' };
  return render(<NavBar locale={locale} />);
}

function getAllLinks(container: HTMLElement): HTMLAnchorElement[] {
  return Array.from(container.querySelectorAll('a'));
}

beforeEach(() => {
  cleanup();
  mockAuthValue.isLoading = false;
  mockAuthValue.user = null;
});

// ─── Preservation 3.3: Admin sees all links ───────────────────────────────────

describe('Preservation 3.3 — Admin NavBar shows full link set', () => {
  /**
   * **Validates: Requirements 3.3**
   * Admin MUST continue to see: Chat, Diagnostic, Patients, Documents, Admin links.
   * MUST PASS on unfixed code.
   */
  it('admin sees Chat link', () => {
    const { container } = renderNavBarWithRole('admin');
    const links = getAllLinks(container);
    const hasChat = links.some((a) => a.getAttribute('href')?.includes('/chat'));
    expect(hasChat).toBe(true);
  });

  it('admin sees Diagnose link', () => {
    const { container } = renderNavBarWithRole('admin');
    const links = getAllLinks(container);
    const hasDiagnose = links.some((a) => a.getAttribute('href')?.includes('/diagnose'));
    expect(hasDiagnose).toBe(true);
  });

  it('admin sees Patients link', () => {
    const { container } = renderNavBarWithRole('admin');
    const links = getAllLinks(container);
    const hasPatients = links.some((a) => a.getAttribute('href')?.includes('/patients'));
    expect(hasPatients).toBe(true);
  });

  it('admin sees Documents link', () => {
    const { container } = renderNavBarWithRole('admin');
    const links = getAllLinks(container);
    const hasDocuments = links.some((a) => a.getAttribute('href')?.includes('/documents'));
    expect(hasDocuments).toBe(true);
  });

  it('admin sees Admin panel link', () => {
    const { container } = renderNavBarWithRole('admin');
    const links = getAllLinks(container);
    const hasAdmin = links.some((a) => a.getAttribute('href')?.endsWith('/admin'));
    expect(hasAdmin).toBe(true);
  });

  it('admin NavBar shows all required links (property test)', () => {
    /**
     * Property: For role='admin', NavBar MUST always include Documents and Admin links.
     * This is the non-buggy behavior that must be preserved.
     */
    fc.assert(
      fc.property(fc.constant('admin'), (role) => {
        cleanup();
        const { container } = renderNavBarWithRole(role);
        const links = getAllLinks(container);
        const hrefs = links.map((a) => a.getAttribute('href') ?? '');

        const hasDocuments = hrefs.some((h) => h.includes('/documents'));
        const hasAdmin = hrefs.some((h) => h.endsWith('/admin'));
        const hasChat = hrefs.some((h) => h.includes('/chat'));
        const hasDiagnose = hrefs.some((h) => h.includes('/diagnose'));
        const hasPatients = hrefs.some((h) => h.includes('/patients'));

        cleanup();
        return hasDocuments && hasAdmin && hasChat && hasDiagnose && hasPatients;
      }),
      { numRuns: 10 },
    );
  });
});

// ─── Preservation 3.5: Medecin sees correct links (no Admin) ─────────────────

describe('Preservation 3.5 — Medecin NavBar shows correct links without Admin', () => {
  /**
   * **Validates: Requirements 3.5**
   * Medecin MUST continue to see: Chat, Diagnostic, Patients, Documents (no Admin).
   * MUST PASS on unfixed code.
   */
  it('medecin sees Chat link', () => {
    const { container } = renderNavBarWithRole('medecin');
    const links = getAllLinks(container);
    const hasChat = links.some((a) => a.getAttribute('href')?.includes('/chat'));
    expect(hasChat).toBe(true);
  });

  it('medecin sees Diagnose link', () => {
    const { container } = renderNavBarWithRole('medecin');
    const links = getAllLinks(container);
    const hasDiagnose = links.some((a) => a.getAttribute('href')?.includes('/diagnose'));
    expect(hasDiagnose).toBe(true);
  });

  it('medecin sees Patients link', () => {
    const { container } = renderNavBarWithRole('medecin');
    const links = getAllLinks(container);
    const hasPatients = links.some((a) => a.getAttribute('href')?.includes('/patients'));
    expect(hasPatients).toBe(true);
  });

  it('medecin sees Documents link', () => {
    const { container } = renderNavBarWithRole('medecin');
    const links = getAllLinks(container);
    const hasDocuments = links.some((a) => a.getAttribute('href')?.includes('/documents'));
    expect(hasDocuments).toBe(true);
  });

  it('medecin does NOT see Admin link', () => {
    const { container } = renderNavBarWithRole('medecin');
    const links = getAllLinks(container);
    const hasAdmin = links.some((a) => a.getAttribute('href')?.endsWith('/admin'));
    expect(hasAdmin).toBe(false);
  });
});

// ─── Preservation 3.4: Non-admin roles never see Admin link ──────────────────

describe('Preservation 3.4 — Non-admin roles never see Admin link', () => {
  /**
   * **Validates: Requirements 3.4**
   * Property: For all non-admin roles, NavBar MUST never show the Admin link.
   * This is already correct behavior on unfixed code — must be preserved.
   * MUST PASS on unfixed code.
   */
  it('medecin does not see admin link', () => {
    const { container } = renderNavBarWithRole('medecin');
    const links = getAllLinks(container);
    const hasAdmin = links.some((a) => a.getAttribute('href')?.endsWith('/admin'));
    expect(hasAdmin).toBe(false);
  });

  it('infirmière does not see admin link', () => {
    const { container } = renderNavBarWithRole('infirmière');
    const links = getAllLinks(container);
    const hasAdmin = links.some((a) => a.getAttribute('href')?.endsWith('/admin'));
    expect(hasAdmin).toBe(false);
  });

  it('for all non-admin roles, admin link is never shown (property test)', () => {
    /**
     * **Validates: Requirements 3.4**
     * Property: For all roles NOT equal to 'admin', NavBar MUST never include admin link.
     * MUST PASS on unfixed code.
     */
    fc.assert(
      fc.property(
        fc.constantFrom('medecin', 'infirmière'),
        (role) => {
          cleanup();
          const { container } = renderNavBarWithRole(role);
          const links = getAllLinks(container);
          const hasAdmin = links.some((a) => a.getAttribute('href')?.endsWith('/admin'));
          cleanup();
          // Preservation: non-admin roles must never see admin link
          return !hasAdmin;
        },
      ),
      { numRuns: 20 },
    );
  });
});

// ─── Preservation 3.2: NavBar shows signin link for unauthenticated users ────

describe('Preservation 3.2 — NavBar returns null for unauthenticated users (current behavior)', () => {
  /**
   * **Validates: Requirements 2.8**
   * After the fix (task 3.1): NavBar renders for guests with a signin link.
   * The old "return null" behavior is intentionally replaced by the RBAC fix.
   */
  it('NavBar renders signin link when user is null (current behavior)', () => {
    mockAuthValue.user = null;
    mockAuthValue.isLoading = false;
    const { container } = render(<NavBar locale="fr" />);
    // After RBAC fix: NavBar renders for guests with signin link
    const nav = container.querySelector('nav');
    expect(nav).not.toBeNull();
    const links = Array.from(container.querySelectorAll('a'));
    const hasSignin = links.some((a) => a.getAttribute('href')?.includes('/login'));
    expect(hasSignin).toBe(true);
  });

  it('NavBar renders signin link for unauthenticated users (property test)', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('fr', 'en'),
        (locale) => {
          cleanup();
          mockAuthValue.user = null;
          mockAuthValue.isLoading = false;
          const { container } = render(<NavBar locale={locale} />);
          const nav = container.querySelector('nav');
          const links = Array.from(container.querySelectorAll('a'));
          const hasSignin = links.some((a) => a.getAttribute('href')?.includes('/login'));
          cleanup();
          return nav !== null && hasSignin;
        },
      ),
      { numRuns: 10 },
    );
  });
});

// ─── Preservation 3.8: Admin panel link only for admin ───────────────────────

describe('Preservation 3.8 — Admin panel link exclusively for admin role', () => {
  /**
   * **Validates: Requirements 3.8**
   * Admin panel link MUST only appear for admin role.
   * MUST PASS on unfixed code.
   */
  it('only admin sees admin panel link (property test)', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('admin', 'medecin', 'infirmière'),
        (role) => {
          cleanup();
          const { container } = renderNavBarWithRole(role);
          const links = getAllLinks(container);
          const hasAdmin = links.some((a) => a.getAttribute('href')?.endsWith('/admin'));
          cleanup();
          // Admin sees admin link; others do not
          return role === 'admin' ? hasAdmin : !hasAdmin;
        },
      ),
      { numRuns: 30 },
    );
  });
});
