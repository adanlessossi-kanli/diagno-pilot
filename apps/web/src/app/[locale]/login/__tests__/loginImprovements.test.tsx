/**
 * Unit tests for Login Page UX improvements
 * Validates: Requirements 1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 1.8
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockLogin = vi.fn();
const mockPush = vi.fn();
const mockReplace = vi.fn();

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

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function renderLoginPage() {
  const { default: LoginPage } = await import('../page');
  return render(<LoginPage />);
}

function getPasswordInput() {
  return document.getElementById('password') as HTMLInputElement;
}

function getEmailInput() {
  return document.getElementById('email') as HTMLInputElement;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('LoginPage — password visibility toggle (Req 1.1, 1.2)', () => {
  it('renders password field as type="password" by default', async () => {
    await renderLoginPage();
    const passwordInput = getPasswordInput();
    expect(passwordInput).toHaveAttribute('type', 'password');
  });

  it('toggles password field to type="text" when toggle button is clicked', async () => {
    await renderLoginPage();
    const passwordInput = getPasswordInput();
    const toggleButton = screen.getByRole('button', { name: /show password/i });

    fireEvent.click(toggleButton);
    expect(passwordInput).toHaveAttribute('type', 'text');
  });

  it('toggles password field back to type="password" on second click', async () => {
    await renderLoginPage();
    const passwordInput = getPasswordInput();
    const toggleButton = screen.getByRole('button', { name: /show password/i });

    fireEvent.click(toggleButton);
    expect(passwordInput).toHaveAttribute('type', 'text');

    // After toggling, the button label changes to "Hide password"
    const hideButton = screen.getByRole('button', { name: /hide password/i });
    fireEvent.click(hideButton);
    expect(passwordInput).toHaveAttribute('type', 'password');
  });
});

describe('LoginPage — forgot password link (Req 1.3)', () => {
  it('renders a "Forgot password" link pointing to /{locale}/forgot-password', async () => {
    await renderLoginPage();
    const link = screen.getByText('forgotPassword');
    expect(link).toBeDefined();
    expect(link.closest('a')).toHaveAttribute('href', '/fr/forgot-password');
  });
});

describe('LoginPage — loading label (Req 1.5)', () => {
  it('shows localized signing-in text while submitting', async () => {
    // Make login hang so we can observe the loading state
    mockLogin.mockImplementation(() => new Promise(() => {}));
    await renderLoginPage();

    fireEvent.change(getEmailInput(), {
      target: { value: 'doc@test.com' },
    });
    fireEvent.change(getPasswordInput(), {
      target: { value: 'password123' },
    });

    await act(async () => {
      fireEvent.submit(screen.getByRole('button', { name: /submit/i }).closest('form')!);
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /signingIn/i })).toBeDefined();
    });
  });
});

describe('LoginPage — inline validation (Req 1.6, 1.7, 1.8)', () => {
  it('shows email required error when submitting with empty email', async () => {
    await renderLoginPage();

    await act(async () => {
      fireEvent.submit(screen.getByRole('button', { name: /submit/i }).closest('form')!);
    });

    await waitFor(() => {
      expect(screen.getByText('emailRequired')).toBeDefined();
    });

    // Should not call login
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('shows password required error when submitting with empty password', async () => {
    await renderLoginPage();

    fireEvent.change(getEmailInput(), {
      target: { value: 'doc@test.com' },
    });

    await act(async () => {
      fireEvent.submit(screen.getByRole('button', { name: /submit/i }).closest('form')!);
    });

    await waitFor(() => {
      expect(screen.getByText('passwordRequired')).toBeDefined();
    });

    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('shows email invalid error when submitting with invalid email format', async () => {
    await renderLoginPage();

    fireEvent.change(getEmailInput(), {
      target: { value: 'not-an-email' },
    });
    fireEvent.change(getPasswordInput(), {
      target: { value: 'password123' },
    });

    await act(async () => {
      fireEvent.submit(screen.getByRole('button', { name: /submit/i }).closest('form')!);
    });

    await waitFor(() => {
      expect(screen.getByText('emailInvalid')).toBeDefined();
    });

    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('does not show validation errors when form is valid', async () => {
    mockLogin.mockResolvedValue(undefined);
    await renderLoginPage();

    fireEvent.change(getEmailInput(), {
      target: { value: 'doc@test.com' },
    });
    fireEvent.change(getPasswordInput(), {
      target: { value: 'password123' },
    });

    await act(async () => {
      fireEvent.submit(screen.getByRole('button', { name: /submit/i }).closest('form')!);
    });

    expect(screen.queryByText('emailRequired')).toBeNull();
    expect(screen.queryByText('passwordRequired')).toBeNull();
    expect(screen.queryByText('emailInvalid')).toBeNull();
    expect(mockLogin).toHaveBeenCalledWith('doc@test.com', 'password123');
  });
});
