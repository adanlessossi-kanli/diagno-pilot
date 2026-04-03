/**
 * Unit test for LoginPage rendering the loginSide image
 * Validates: Requirement 2.1
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';
import { IMAGES } from '@/lib/images';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'fr',
}));
  useAuth: () => ({
    user: null,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
});

describe('LoginPage — unit tests', () => {
  it('LoginPage renders IMAGES.loginSide', async () => {
    const { default: LoginPage } = await import('../page');
    render(<LoginPage />);
    // Use getAllByRole since the page now has both the side image and the SVG logo
    const imgs = screen.getAllByRole('img');
    const sideImg = imgs.find((el) =>
      el.getAttribute('src')?.includes(IMAGES.loginSide.src) ||
      el.getAttribute('alt') === IMAGES.loginSide.alt
    );
    expect(sideImg).toBeDefined();
    expect(sideImg).toHaveAttribute('src', expect.stringContaining(IMAGES.loginSide.src));
  });
});
