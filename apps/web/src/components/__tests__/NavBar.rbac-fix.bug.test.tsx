/**
 * Bug condition exploration tests — RBAC Fix bugfix spec
 *
 * These tests assert the EXPECTED (correct) behavior and will FAIL on unfixed
 * code, proving each bug exists. DO NOT fix the code when these fail.
 *
 * **Validates: Requirements 1.1, 1.6, 1.7, 2.1, 2.6, 2.7, 2.8**
 *
 * Bugs confirmed by this file:
 *   - Bug 1: NavBar shows Documents link for infirmière (should be absent)
 *   - Bug 2: NavBar shows no "Se connecter" link for guest/unauthenticated users
 *   - Bug 7 (NavBar medecin): NavBar shows Documents link for medecin (expected behavior)
 *   - Property: NavBar shows exactly the links defined in ROLE_NAV_LINKS for each role
 *
 * Expected counterexamples (on unfixed code):
 *   - infirmière: links[] contains href including '/documents' → Documents link present (bug)
 *   - guest (user=null): NavBar returns null → no "Se connecter" link rendered (bug)
 *   - medecin: links[] contains href including '/documents' → Documents link present (correct)
 *   - Property: infirmière sees Documents (not in ROLE_NAV_LINKS for infirmière)
 *   - Property: guest sees no signin link (not in rendered links)
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

// ─── ROLE_NAV_LINKS map ───────────────────────────────────────────────────────
// guest → [signin]
// infirmière → [chat, diagnose, patients]
// medecin → [chat, diagnose, patients, documents]
// admin → [chat, diagnose, patients, documents, admin]

const ROLE_NAV_LINKS: Record<string, string[]> = {
  guest: ['signin'],
  'infirmière': ['chat', 'diagnose', 'patients'],
  medecin: ['chat', 'diagnose', 'patients', 'documents'],
  admin: ['chat', 'diagnose', 'patients', 'documents', 'admin'],
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function renderNavBarWithRole(role: string, locale: string = 'fr') {
  mockAuthValue.user = { id: '1', email: 'user@test.com', role, fullName: 'Test User' };
  return render(<NavBar locale={locale} />);
}

function renderNavBarAsGuest(locale: string = 'fr') {
  mockAuthValue.user = null;
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

// ─── Bug 1: NavBar shows Documents link for infirmière ────────────────────────

describe('Bug 1 — NavBar Documents link absent for infirmière', () => {
  /**
   * **Validates: Requirements 1.1, 1.6, 2.1, 2.6**
   * NavBar MUST NOT show Documents link for infirmière.
   * EXPECTED TO FAIL on unfixed code — Documents link IS present for infirmière.
   * Counterexample: links contains href including '/documents' for role='infirmière'.
   */
  it('infirmière does NOT see Documents link in NavBar', () => {
    const { container } = renderNavBarWithRole('infirmière');
    const links = getAllLinks(container);
    const hasDocuments = links.some((a) => a.getAttribute('href')?.includes('/documents'));
    // BUG 1: will be true on unfixed code (Documents link IS present)
    expect(hasDocuments).toBe(false);
  });

  it('infirmière DOES see Chat link in NavBar', () => {
    const { container } = renderNavBarWithRole('infirmière');
    const links = getAllLinks(container);
    const hasChat = links.some((a) => a.getAttribute('href')?.includes('/chat'));
    // This should pass — chat is in infirmière's allowed links
    expect(hasChat).toBe(true);
  });
});

// ─── Bug 2: NavBar shows no "Se connecter" link for guest ─────────────────────

describe('Bug 2 — NavBar "Se connecter" link absent for guest', () => {
  /**
   * **Validates: Requirements 1.7, 2.8**
   * NavBar MUST show a "Se connecter" / signin link for unauthenticated users.
   * EXPECTED TO FAIL on unfixed code — NavBar returns null for unauthenticated users.
   * Counterexample: NavBar renders null (no nav element) when user=null.
   */
  it('guest (user=null) sees a signin / "Se connecter" link in NavBar', () => {
    const { container } = renderNavBarAsGuest();
    const links = getAllLinks(container);
    // BUG 2: NavBar returns null for unauthenticated users on unfixed code
    // so no links are rendered at all — signin link is absent
    const hasSignin = links.some(
      (a) =>
        a.getAttribute('href')?.includes('/login') ||
        a.textContent?.toLowerCase().includes('connecter') ||
        a.textContent?.toLowerCase().includes('signin') ||
        a.textContent?.toLowerCase().includes('login'),
    );
    expect(hasSignin).toBe(true);
  });

  it('guest NavBar renders a nav element (not null)', () => {
    const { container } = renderNavBarAsGuest();
    // BUG 2: NavBar returns null for unauthenticated users on unfixed code
    const nav = container.querySelector('nav');
    expect(nav).not.toBeNull();
  });
});

// ─── Bug 7 (NavBar medecin): Documents link IS present for medecin ────────────

describe('Bug 7 (NavBar medecin) — Documents link present for medecin', () => {
  /**
   * **Validates: Requirements 2.7**
   * NavBar MUST show Documents link for medecin (this is expected behavior).
   * This test verifies the ROLE_NAV_LINKS map includes documents for medecin.
   * On unfixed code: medecin sees Documents (correct) but infirmière also sees it (bug).
   */
  it('medecin DOES see Documents link in NavBar', () => {
    const { container } = renderNavBarWithRole('medecin');
    const links = getAllLinks(container);
    const hasDocuments = links.some((a) => a.getAttribute('href')?.includes('/documents'));
    // medecin should see Documents — this is the expected behavior
    expect(hasDocuments).toBe(true);
  });
});

// ─── Property: NavBar shows exactly the links defined in ROLE_NAV_LINKS ───────

describe('Property — NavBar shows exactly the links defined in ROLE_NAV_LINKS', () => {
  /**
   * **Validates: Requirements 2.1, 2.6, 2.7, 2.8**
   * For all roles in ['infirmière', 'guest', 'medecin', 'admin'],
   * NavBar shows exactly the links defined in ROLE_NAV_LINKS map.
   *
   * EXPECTED TO FAIL on unfixed code for:
   *   - infirmière: sees Documents (not in ROLE_NAV_LINKS['infirmière'])
   *   - guest: NavBar returns null (no signin link rendered)
   *
   * Counterexample: role='infirmière' → Documents link present (should be absent)
   */
  it('infirmière NavBar links match ROLE_NAV_LINKS (property test)', () => {
    fc.assert(
      fc.property(fc.constant('infirmière'), (role) => {
        cleanup();
        const { container } = renderNavBarWithRole(role);
        const links = getAllLinks(container);
        const hrefs = links.map((a) => a.getAttribute('href') ?? '');

        // Documents must NOT be present for infirmière
        const hasDocuments = hrefs.some((h) => h.includes('/documents'));
        // Chat MUST be present for infirmière
        const hasChat = hrefs.some((h) => h.includes('/chat'));

        cleanup();
        // BUG 1: hasDocuments is true on unfixed code → property fails
        return !hasDocuments && hasChat;
      }),
      { numRuns: 10 },
    );
  });

  it('guest NavBar shows signin link (property test)', () => {
    fc.assert(
      fc.property(fc.constant('guest'), (_role) => {
        cleanup();
        mockAuthValue.user = null;
        const { container } = render(<NavBar locale="fr" />);
        const links = getAllLinks(container);
        const hasSignin = links.some(
          (a) =>
            a.getAttribute('href')?.includes('/login') ||
            a.textContent?.toLowerCase().includes('connecter'),
        );
        cleanup();
        // BUG 2: NavBar returns null for guest on unfixed code → no signin link
        return hasSignin;
      }),
      { numRuns: 10 },
    );
  });

  it('medecin NavBar includes Documents and excludes Admin (property test)', () => {
    fc.assert(
      fc.property(fc.constant('medecin'), (role) => {
        cleanup();
        const { container } = renderNavBarWithRole(role);
        const links = getAllLinks(container);
        const hrefs = links.map((a) => a.getAttribute('href') ?? '');

        const hasDocuments = hrefs.some((h) => h.includes('/documents'));
        const hasAdmin = hrefs.some((h) => h.endsWith('/admin'));

        cleanup();
        return hasDocuments && !hasAdmin;
      }),
      { numRuns: 10 },
    );
  });

  it('admin NavBar includes Documents and Admin (property test)', () => {
    fc.assert(
      fc.property(fc.constant('admin'), (role) => {
        cleanup();
        const { container } = renderNavBarWithRole(role);
        const links = getAllLinks(container);
        const hrefs = links.map((a) => a.getAttribute('href') ?? '');

        const hasDocuments = hrefs.some((h) => h.includes('/documents'));
        const hasAdmin = hrefs.some((h) => h.endsWith('/admin'));

        cleanup();
        return hasDocuments && hasAdmin;
      }),
      { numRuns: 10 },
    );
  });

  it('for all roles, NavBar links match ROLE_NAV_LINKS constraints (property test)', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('infirmière', 'medecin', 'admin'),
        (role) => {
          cleanup();
          const { container } = renderNavBarWithRole(role);
          const links = getAllLinks(container);
          const hrefs = links.map((a) => a.getAttribute('href') ?? '');

          const allowedLinks = ROLE_NAV_LINKS[role] ?? [];
          const shouldHaveDocuments = allowedLinks.includes('documents');
          const hasDocuments = hrefs.some((h) => h.includes('/documents'));

          cleanup();
          // BUG 1: infirmière has documents in links on unfixed code
          return hasDocuments === shouldHaveDocuments;
        },
      ),
      { numRuns: 30 },
    );
  });
});
