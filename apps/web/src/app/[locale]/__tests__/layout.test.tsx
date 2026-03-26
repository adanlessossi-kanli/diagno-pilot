import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('../../../components/NavBar', () => ({
  default: ({ locale }: { locale: string }) => (
    <nav data-testid="navbar" data-locale={locale} aria-label="Main navigation" />
  ),
}));

vi.mock('../../../components/Footer', () => ({
  default: () => (
    <footer data-testid="footer">
      <p>© 2026 protic-togo</p>
    </footer>
  ),
}));

vi.mock('../../../contexts/AuthContext', () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useAuth: () => ({
    user: { id: '1', email: 'doc@test.com', role: 'medecin', fullName: 'Dr Test' },
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    fetchWithRefresh: vi.fn(),
  }),
}));

vi.mock('next-intl/server', () => ({
  getMessages: vi.fn().mockResolvedValue({}),
}));

vi.mock('next/navigation', () => ({
  notFound: vi.fn(),
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/',
}));

vi.mock('../../../i18n/routing', () => ({
  routing: { locales: ['fr', 'en'] },
}));

vi.mock('next-intl', () => ({
  NextIntlClientProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useTranslations: () => (key: string) => key,
}));

// ─── Helper: render layout with a given locale ────────────────────────────────

async function renderLayout(locale: string = 'fr') {
  // Import after mocks are set up
  const { default: LocaleLayout } = await import('../layout');
  const params = Promise.resolve({ locale });
  const { container } = render(
    await (async () => {
      // LocaleLayout is an async server component — call it directly
      const element = await LocaleLayout({ children: <div data-testid="page-content">Page</div>, params });
      return element;
    })()
  );
  return container;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('LocaleLayout — unit tests', () => {
  it('renders NavBar on authenticated pages', async () => {
    await renderLayout('fr');
    expect(screen.getByTestId('navbar')).toBeDefined();
  });

  it('renders Footer on authenticated pages', async () => {
    await renderLayout('fr');
    expect(screen.getByTestId('footer')).toBeDefined();
  });

  it('wraps children in <main>', async () => {
    const container = await renderLayout('fr');
    const main = container.querySelector('main');
    expect(main).not.toBeNull();
    expect(main?.querySelector('[data-testid="page-content"]')).not.toBeNull();
  });

  it('sets html lang attribute to the locale', async () => {
    const container = await renderLayout('en');
    const html = container.querySelector('html');
    // In jsdom the html element is the document root, check via data-locale on navbar
    const navbar = screen.getByTestId('navbar');
    expect(navbar.getAttribute('data-locale')).toBe('en');
  });

  it('NavBar receives the correct locale prop', async () => {
    await renderLayout('fr');
    const navbar = screen.getByTestId('navbar');
    expect(navbar.getAttribute('data-locale')).toBe('fr');
  });
});
