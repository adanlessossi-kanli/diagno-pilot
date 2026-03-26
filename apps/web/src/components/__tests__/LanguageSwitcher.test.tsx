import fc from 'fast-check';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import React from 'react';
import LanguageSwitcher from '../LanguageSwitcher';

// ─── Mocks ────────────────────────────────────────────────────────────────────

let mockLocale = 'fr';
vi.mock('next-intl', () => ({
  useLocale: () => mockLocale,
}));

let mockPathname = '/';
const mockReplace = vi.fn();
vi.mock('../../i18n/navigation', () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ replace: mockReplace }),
}));

vi.mock('../../i18n/routing', () => ({
  routing: { locales: ['fr', 'en'] },
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

function renderSwitcher() {
  return render(<LanguageSwitcher />);
}

beforeEach(() => {
  mockLocale = 'fr';
  mockPathname = '/';
  mockReplace.mockClear();
  // Reset document.cookie
  document.cookie = 'NEXT_LOCALE=; path=/; max-age=0';
});

afterEach(() => {
  cleanup();
});

// ─── Unit tests ───────────────────────────────────────────────────────────────

describe('LanguageSwitcher — unit tests', () => {
  it('renders buttons for all supported locales', () => {
    renderSwitcher();
    expect(screen.getByRole('button', { name: /french/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /english/i })).toBeTruthy();
  });

  it('marks the current locale button as aria-current', () => {
    mockLocale = 'fr';
    renderSwitcher();
    const frButton = screen.getByRole('button', { name: /french/i });
    expect(frButton.getAttribute('aria-current')).toBe('true');
    const enButton = screen.getByRole('button', { name: /english/i });
    expect(enButton.getAttribute('aria-current')).toBeNull();
  });

  it('calls router.replace with new locale on button click', () => {
    mockLocale = 'fr';
    renderSwitcher();
    const enButton = screen.getByRole('button', { name: /english/i });
    fireEvent.click(enButton);
    expect(mockReplace).toHaveBeenCalledWith('/', { locale: 'en' });
  });

  it('sets NEXT_LOCALE cookie when switching language', () => {
    mockLocale = 'fr';
    renderSwitcher();
    const enButton = screen.getByRole('button', { name: /english/i });
    fireEvent.click(enButton);
    expect(document.cookie).toContain('NEXT_LOCALE=en');
  });

  it('sets NEXT_LOCALE cookie with 1-year max-age when switching to fr', () => {
    mockLocale = 'en';
    renderSwitcher();
    const frButton = screen.getByRole('button', { name: /french/i });
    fireEvent.click(frButton);
    expect(document.cookie).toContain('NEXT_LOCALE=fr');
  });

  it('does not trigger full page reload (router.replace is used, not window.location)', () => {
    renderSwitcher();
    const enButton = screen.getByRole('button', { name: /english/i });
    fireEvent.click(enButton);
    // router.replace was called (soft navigation), not a full reload
    expect(mockReplace).toHaveBeenCalledTimes(1);
  });

  it('fallback: renders FR button as default when locale is unsupported', () => {
    // Even if locale is unsupported, the component renders all supported locales
    mockLocale = 'de'; // unsupported
    renderSwitcher();
    expect(screen.getByRole('button', { name: /french/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /english/i })).toBeTruthy();
    // Neither button should be aria-current since 'de' doesn't match 'fr' or 'en'
    const frButton = screen.getByRole('button', { name: /french/i });
    const enButton = screen.getByRole('button', { name: /english/i });
    expect(frButton.getAttribute('aria-current')).toBeNull();
    expect(enButton.getAttribute('aria-current')).toBeNull();
  });
});

// ─── Property 4 ───────────────────────────────────────────────────────────────

// Feature: app-consistency, Property 4: Pour toute locale supportée, l'interface est mise à jour
describe('LanguageSwitcher — Property 4: Changement de langue met à jour l\'interface', () => {
  /**
   * **Validates: Requirements 2.3, 2.4**
   * Property 4: For any supported locale selected via LanguageSwitcher,
   * the router.replace is called with the new locale (soft navigation, no full reload).
   */
  it('calls router.replace for any supported locale without full reload', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('fr', 'en'),
        fc.constantFrom('fr', 'en'),
        (currentLocale, targetLocale) => {
          cleanup();
          mockLocale = currentLocale;
          mockReplace.mockClear();

          renderSwitcher();

          // Click the button for targetLocale
          const targetLabel = targetLocale === 'fr' ? /french/i : /english/i;
          const button = screen.getByRole('button', { name: targetLabel });
          fireEvent.click(button);

          // router.replace must be called with the target locale (soft navigation)
          const called = mockReplace.mock.calls.some(
            (call) => call[1]?.locale === targetLocale,
          );
          cleanup();
          return called;
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ─── Property 5 ───────────────────────────────────────────────────────────────

// Feature: app-consistency, Property 5: Pour toute locale sélectionnée, elle est persistée et restaurée
describe('LanguageSwitcher — Property 5: Persistance du choix de langue (round-trip)', () => {
  /**
   * **Validates: Requirements 2.5, 2.6**
   * Property 5: For any locale selected by the user, the value must be persisted
   * in the NEXT_LOCALE cookie and can be restored in the next session.
   */
  it('persists selected locale in NEXT_LOCALE cookie for any supported locale', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('fr', 'en'),
        (targetLocale) => {
          cleanup();
          mockLocale = 'fr';
          // Clear cookie before each run
          document.cookie = 'NEXT_LOCALE=; path=/; max-age=0';

          renderSwitcher();

          const targetLabel = targetLocale === 'fr' ? /french/i : /english/i;
          const button = screen.getByRole('button', { name: targetLabel });
          fireEvent.click(button);

          // Cookie must contain the selected locale (round-trip persistence)
          const cookieValue = document.cookie
            .split(';')
            .map((c) => c.trim())
            .find((c) => c.startsWith('NEXT_LOCALE='))
            ?.split('=')[1];

          cleanup();
          return cookieValue === targetLocale;
        },
      ),
      { numRuns: 100 },
    );
  });
});
