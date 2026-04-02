/**
 * Bug condition exploration tests — UI/UX Navigation Overhaul
 *
 * These tests assert the EXPECTED (correct) behavior and will FAIL on unfixed
 * code, proving each bug exists. DO NOT fix the code when these fail.
 *
 * **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.7**
 *
 * Bugs confirmed by this file:
 *   - Bug 1.1: NavBar has no SVG logo with data-logo="diagno-pilot"
 *   - Bug 1.2: LoginPage has no SVG logo with data-logo="diagno-pilot"
 *   - Bug 1.3: HomePage hero has no min-h-screen class and no /chat CTA link
 *   - Bug 1.4: NavBar first link is "Accueil"/"Home" not "Assistant Q&A"/"Q&A Assistant"
 *   - Bug 1.5: fr.json has no nav.documents key
 *   - Bug 1.7: admin-panel/page.tsx file does not exist
 *
 * Counterexamples found (documented after running on unfixed code):
 *   - NavBar renders <span>Diagno-Pilot</span> with no SVG element
 *   - LoginPage renders <p>Diagno-Pilot</p> with no SVG element
 *   - HomePage hero div has class "h-64", no min-h-screen, no /chat link
 *   - NavBar links[0].textContent is "home" (translation key) = "Accueil"
 *   - fr.json nav object has keys: home, chat, diagnose, patients, admin, logout — no "documents"
 *   - File apps/web/src/app/[locale]/admin-panel/page.tsx does not exist
 */

import fc from 'fast-check';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import React from 'react';
import * as fs from 'fs';
import * as path from 'path';
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

vi.mock('next/image', () => ({
  default: ({ src, alt, ...props }: { src: string; alt: string; [key: string]: unknown }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} {...props} />
  ),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useParams: () => ({ locale: 'fr-TG' }),
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

function renderNavBar(role: string = 'admin', locale: string = 'fr') {
  mockAuthValue.user = { id: '1', email: 'admin@test.com', role, fullName: 'Admin' };
  return render(<NavBar locale={locale} />);
}

beforeEach(() => {
  cleanup();
  mockAuthValue.isLoading = false;
});

// ─── Bug 1.1: NavBar has no SVG logo ─────────────────────────────────────────

describe('Bug 1.1 — NavBar SVG logo absent', () => {
  /**
   * **Validates: Requirements 1.1, 2.1**
   * NavBar MUST render an SVG with data-logo="diagno-pilot".
   * EXPECTED TO FAIL on unfixed code — NavBar only has a plain <span>.
   * Counterexample: querySelector('[data-logo="diagno-pilot"]') returns null.
   */
  it('NavBar renders SVG logo with data-logo="diagno-pilot" for admin user', () => {
    const { container } = renderNavBar('admin');
    const logo = container.querySelector('[data-logo="diagno-pilot"]');
    // BUG 1.1: will be null on unfixed code (no SVG logo exists)
    expect(logo).not.toBeNull();
  });

  it('NavBar renders SVG logo for any role (property test)', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('admin', 'medecin', 'guest', 'infirmière'),
        (role) => {
          cleanup();
          const { container } = renderNavBar(role);
          const logo = container.querySelector('[data-logo="diagno-pilot"]');
          cleanup();
          // BUG 1.1: will be null for all roles on unfixed code
          return logo !== null;
        },
      ),
      { numRuns: 4 },
    );
  });
});

// ─── Bug 1.2: LoginPage has no SVG logo ──────────────────────────────────────

describe('Bug 1.2 — LoginPage SVG logo absent', () => {
  /**
   * **Validates: Requirements 1.2, 2.2**
   * LoginPage MUST render an SVG with data-logo="diagno-pilot".
   * EXPECTED TO FAIL on unfixed code — LoginPage only has a plain <p>.
   * Counterexample: querySelector('[data-logo="diagno-pilot"]') returns null.
   */
  it('LoginPage renders SVG logo with data-logo="diagno-pilot"', async () => {
    // Dynamically import to avoid issues with server components
    const { default: LoginPage } = await import('../../app/[locale]/login/page');
    const { container } = render(<LoginPage />);
    const logo = container.querySelector('[data-logo="diagno-pilot"]');
    // BUG 1.2: will be null on unfixed code (no SVG logo on login page)
    expect(logo).not.toBeNull();
  });
});

// ─── Bug 1.3: HomePage hero has no min-h-screen and no /chat CTA ─────────────

describe('Bug 1.3 — HomePage hero inadequate', () => {
  /**
   * **Validates: Requirements 1.3, 2.3**
   * HomePage hero section MUST have min-h-screen class AND a link to /chat.
   * EXPECTED TO FAIL on unfixed code — hero is h-64 with no CTA.
   * Counterexample: hero div has class "h-64", no min-h-screen, no /chat link.
   */
  it('HomePage hero section has min-h-screen class', async () => {
    const { default: HomePage } = await import('../../app/[locale]/page');
    const { container } = render(<HomePage />);
    // BUG 1.3: hero div has "h-64" not "min-h-screen" on unfixed code
    const heroWithMinH = container.querySelector('.min-h-screen');
    expect(heroWithMinH).not.toBeNull();
  });

  it('HomePage hero section has a link to /chat', async () => {
    const { default: HomePage } = await import('../../app/[locale]/page');
    const { container } = render(<HomePage />);
    const links = Array.from(container.querySelectorAll('a'));
    const chatLink = links.find((a) => a.getAttribute('href')?.includes('/chat'));
    // BUG 1.3: no /chat CTA link on unfixed code
    expect(chatLink).not.toBeUndefined();
  });
});

// ─── Bug 1.4: NavBar first link is "Accueil" not "Assistant Q&A" ─────────────

describe('Bug 1.4 — NavBar wrong link order', () => {
  /**
   * **Validates: Requirements 1.4, 2.4**
   * For admin user, NavBar first link MUST NOT be "Accueil"/"Home"/"home".
   * It should be "Assistant Q&A" / "chat" (the translation key).
   * EXPECTED TO FAIL on unfixed code — first link IS "home" (Accueil).
   * Counterexample: links[0].textContent === "home" (i18n key for Accueil).
   */
  it('NavBar first link for admin is not "home" (Accueil)', () => {
    const { container } = renderNavBar('admin');
    const desktopLinks = container.querySelectorAll('.hidden.md\\:flex a');
    const firstLink = desktopLinks[0];
    // BUG 1.4: first link is "home" on unfixed code
    expect(firstLink).not.toBeUndefined();
    const text = firstLink?.textContent?.toLowerCase() ?? '';
    expect(text).not.toBe('home');
    expect(text).not.toBe('accueil');
    expect(text).not.toContain('home');
  });

  it('NavBar first link for admin is "chat" (Q&A Assistant)', () => {
    const { container } = renderNavBar('admin');
    const desktopLinks = container.querySelectorAll('.hidden.md\\:flex a');
    const firstLink = desktopLinks[0];
    // BUG 1.4: first link should be "chat" not "home"
    expect(firstLink?.textContent).toBe('chat');
  });

  it('NavBar first link is not "home" for any role (property test)', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('admin', 'medecin', 'guest', 'infirmière'),
        (role) => {
          cleanup();
          const { container } = renderNavBar(role);
          const desktopLinks = container.querySelectorAll('.hidden.md\\:flex a');
          const firstLink = desktopLinks[0];
          const text = firstLink?.textContent?.toLowerCase() ?? '';
          cleanup();
          // BUG 1.4: first link is "home" on unfixed code for all roles
          return text !== 'home' && text !== 'accueil';
        },
      ),
      { numRuns: 4 },
    );
  });
});

// ─── Bug 1.5: fr.json missing nav.documents key ───────────────────────────────

describe('Bug 1.5 — fr.json missing nav.documents key', () => {
  /**
   * **Validates: Requirements 1.5, 2.5**
   * fr.json MUST have nav.documents key defined.
   * EXPECTED TO FAIL on unfixed code — nav.documents is absent.
   * Counterexample: fr.json nav object has no "documents" key.
   */
  it('fr.json has nav.documents key defined', () => {
    const frJsonPath = path.resolve(
      __dirname,
      '../../../../../packages/i18n/locales/fr.json',
    );
    const frJson = JSON.parse(fs.readFileSync(frJsonPath, 'utf-8'));
    // BUG 1.5: nav.documents is missing on unfixed code
    expect(frJson.nav).toBeDefined();
    expect(frJson.nav.documents).toBeDefined();
  });

  it('en.json has nav.documents key defined', () => {
    const enJsonPath = path.resolve(
      __dirname,
      '../../../../../packages/i18n/locales/en.json',
    );
    const enJson = JSON.parse(fs.readFileSync(enJsonPath, 'utf-8'));
    // BUG 1.5: nav.documents is missing on unfixed code
    expect(enJson.nav).toBeDefined();
    expect(enJson.nav.documents).toBeDefined();
  });
});

// ─── Bug 1.7: admin panel route file absent ──────────────────────────────────

describe('Bug 1.7 — admin panel route file absent', () => {
  /**
   * **Validates: Requirements 1.7, 2.7**
   * File apps/web/src/app/[locale]/admin/page.tsx MUST exist (admin panel).
   * EXPECTED TO FAIL on unfixed code — file does not exist.
   * Counterexample: fs.existsSync returns false.
   */
  it('admin/page.tsx file exists (admin panel)', () => {
    const adminPanelPath = path.resolve(
      __dirname,
      '../../app/[locale]/admin/page.tsx',
    );
    // BUG 1.7: file does not exist on unfixed code
    expect(fs.existsSync(adminPanelPath)).toBe(true);
  });
});
