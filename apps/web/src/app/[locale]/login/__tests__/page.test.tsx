/**
 * Page-level tests for LoginPage
 * Validates: Requirements 7.1, 7.2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockPush = vi.fn();
const mockReplace = vi.fn();
const mockLogin = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'fr',
}));

vi.mock('next/image', () => ({
  default: ({ src, alt }: { src: string; alt: string }) =>
    React.createElement('img', { src, alt }),
}));

vi.mock('@/lib/images', () => ({
  IMAGES: {
    loginSide: { src: '/login-side.jpg', alt: 'Login side' },
  },
}));

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: null,
    isLoading: false,
    login: mockLogin,
    logout: vi.fn(),
  }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
}));

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('LoginPage — page-level tests', () => {
  it('renders email and password fields', async () => {
    const { default: LoginPage } = await import('../page');
    render(<LoginPage />);

    expect(screen.getByLabelText(/email/i)).toBeDefined();
    expect(document.getElementById('password')).toBeDefined();
  });

  it('renders the submit button', async () => {
    const { default: LoginPage } = await import('../page');
    render(<LoginPage />);

    expect(screen.getByRole('button', { name: /submit/i })).toBeDefined();
  });

  it('calls login with email and password on valid submission', async () => {
    mockLogin.mockResolvedValue(undefined);
    const { default: LoginPage } = await import('../page');
    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'doc@test.com' },
    });
    fireEvent.change(document.getElementById('password')!, {
      target: { value: 'password123' },
    });

    await act(async () => {
      fireEvent.submit(screen.getByRole('button', { name: /submit/i }).closest('form')!);
    });

    expect(mockLogin).toHaveBeenCalledWith('doc@test.com', 'password123');
  });

  it('does not redirect when login throws (invalid credentials)', async () => {
    mockLogin.mockRejectedValue(new Error('Unauthorized'));
    const { default: LoginPage } = await import('../page');
    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'bad@test.com' },
    });
    fireEvent.change(document.getElementById('password')!, {
      target: { value: 'wrongpass' },
    });

    await act(async () => {
      fireEvent.submit(screen.getByRole('button', { name: /submit/i }).closest('form')!);
    });

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });

    expect(mockPush).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('displays an error message on invalid credentials', async () => {
    mockLogin.mockRejectedValue(new Error('Unauthorized'));
    const { default: LoginPage } = await import('../page');
    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'bad@test.com' },
    });
    fireEvent.change(document.getElementById('password')!, {
      target: { value: 'wrongpass' },
    });

    await act(async () => {
      fireEvent.submit(screen.getByRole('button', { name: /submit/i }).closest('form')!);
    });

    await waitFor(() => {
      const alert = screen.getByRole('alert');
      expect(alert.textContent).toBeTruthy();
    });
  });
});
