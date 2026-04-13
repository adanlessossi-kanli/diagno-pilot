/**
 * Unit tests for LanguageSwitcher accessibility improvements.
 *
 * Validates:
 * - Req 7.2: Minimum 44×44 CSS pixel touch target and 14px font size
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
}));

vi.mock('../i18n/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ replace: vi.fn() }),
}));

vi.mock('../i18n/routing', () => ({
  routing: { locales: ['fr-TG', 'fr-BJ', 'en'] },
}));

// ─── Import component under test ─────────────────────────────────────────────

import LanguageSwitcher from '../components/LanguageSwitcher';

// ─── Teardown ─────────────────────────────────────────────────────────────────

afterEach(() => {
  cleanup();
});

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Parses Tailwind min-w-[Xpx] / min-h-[Xpx] classes and returns the numeric
 * pixel value, or null if not found.
 */
function parseTailwindMinSize(className: string, dimension: 'w' | 'h'): number | null {
  const regex = new RegExp(`min-${dimension}-\\[(\\d+)px\\]`);
  const match = className.match(regex);
  return match ? Number(match[1]) : null;
}

/**
 * Maps Tailwind text-size classes to their pixel equivalents.
 */
function tailwindFontSizePx(className: string): number | null {
  // Tailwind default scale
  const map: Record<string, number> = {
    'text-xs': 12,
    'text-sm': 14,
    'text-base': 16,
    'text-lg': 18,
    'text-xl': 20,
  };
  for (const [cls, px] of Object.entries(map)) {
    if (className.includes(cls)) return px;
  }
  return null;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('LanguageSwitcher accessibility', () => {
  it('each locale button has a minimum 44×44px touch target', () => {
    render(<LanguageSwitcher />);

    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThanOrEqual(1);

    for (const button of buttons) {
      const cls = button.className;
      const minW = parseTailwindMinSize(cls, 'w');
      const minH = parseTailwindMinSize(cls, 'h');

      expect(minW).not.toBeNull();
      expect(minH).not.toBeNull();
      expect(minW!).toBeGreaterThanOrEqual(44);
      expect(minH!).toBeGreaterThanOrEqual(44);
    }
  });

  it('each locale button has a font size of at least 14px', () => {
    render(<LanguageSwitcher />);

    const buttons = screen.getAllByRole('button');

    for (const button of buttons) {
      const fontSize = tailwindFontSizePx(button.className);
      expect(fontSize).not.toBeNull();
      expect(fontSize!).toBeGreaterThanOrEqual(14);
    }
  });

  it('renders all supported locales as buttons', () => {
    render(<LanguageSwitcher />);

    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(3);
    expect(buttons.map((b) => b.textContent)).toEqual(['FR-TG', 'FR-BJ', 'EN']);
  });

  it('marks the current locale button with aria-current', () => {
    render(<LanguageSwitcher />);

    const enButton = screen.getByLabelText('Switch to English');
    expect(enButton.getAttribute('aria-current')).toBe('true');

    // Other buttons should not have aria-current
    const frButtons = screen.getAllByRole('button').filter(
      (b) => b.getAttribute('aria-current') !== 'true'
    );
    expect(frButtons).toHaveLength(2);
  });
});
