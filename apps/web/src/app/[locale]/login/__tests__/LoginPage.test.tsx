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
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock('next/image', () => ({
  default: ({ src, alt }: { src: string; alt: string }) =>
    React.createElement('img', { src, alt }),
}));

vi.mock('../../../../contexts/AuthContext', () => ({
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
    const img = screen.getByRole('img');
    expect(img).toHaveAttribute('src', expect.stringContaining(IMAGES.loginSide.src));
  });
});
