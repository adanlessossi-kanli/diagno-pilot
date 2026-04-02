import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { resolveLocale } from './i18n/routing';

// ---------------------------------------------------------------------------
// Inline helpers mirroring middleware logic (no Next.js runtime needed)
// ---------------------------------------------------------------------------

// Updated to reflect new locale set (Requirements 6.2, 6.6, 9.1)
const SUPPORTED_LOCALES = ['fr-TG', 'fr-BJ', 'en'] as const;
const DEFAULT_LOCALE = 'fr-TG';
const PUBLIC_PATHS = ['/login', '/qa'];

function decodeRoleFromJwt(token: string): string | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const decoded = JSON.parse(atob(payload));
    return typeof decoded.role === 'string' ? decoded.role : null;
  } catch {
    return null;
  }
}

function isPublicPath(pathname: string): boolean {
  if (pathname === '/qa') return true;
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length >= 2) {
    const afterLocale = '/' + segments.slice(1).join('/');
    if (PUBLIC_PATHS.some((p) => afterLocale === p || afterLocale.startsWith(p + '/'))) {
      return true;
    }
  }
  if (pathname === '/login') return true;
  return false;
}

function isQaPath(pathname: string): boolean {
  if (pathname === '/qa') return true;
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length >= 2 && segments[1] === 'qa') return true;
  return false;
}

function extractLocale(pathname: string, cookieLocale?: string): string {
  // Cookie preference overrides browser detection (Requirements 6.4, 6.5)
  if (cookieLocale) {
    const resolved = resolveLocale(cookieLocale);
    return resolved;
  }
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length > 0 && (SUPPORTED_LOCALES as readonly string[]).includes(segments[0])) {
    return segments[0];
  }
  return DEFAULT_LOCALE;
}

type Decision = { type: 'pass' } | { type: 'redirect'; to: string };

function routingDecision(pathname: string, token: string | undefined, cookieLocale?: string): Decision {
  if (isPublicPath(pathname)) return { type: 'pass' };
  const role = token ? decodeRoleFromJwt(token) : null;
  const locale = extractLocale(pathname, cookieLocale);
  if (pathname.includes('/admin') && role !== 'admin') {
    return { type: 'redirect', to: `/${locale}` };
  }
  if (!token && !isQaPath(pathname)) {
    return { type: 'redirect', to: `/${locale}/login` };
  }
  return { type: 'pass' };
}

// ---------------------------------------------------------------------------
// JWT test helper
// ---------------------------------------------------------------------------

function makeJwt(role: string): string {
  const payload = btoa(JSON.stringify({ role, sub: 'user123', exp: 9999999999 }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
  return `header.${payload}.signature`;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const NON_ADMIN_ROLES = ['medecin', 'infirmière', 'guest'] as const;
const PROTECTED_PATHS = [
  '/fr-TG/patients',
  '/fr-TG/diagnose',
  '/fr-TG/chat',
  '/fr-BJ/patients',
  '/fr-BJ/diagnose',
  '/en/patients',
  '/en/diagnose',
  '/en/chat',
] as const;

// ---------------------------------------------------------------------------
// Task 7.2 — Property 8: Middleware redirige les non-admins hors de /admin
// ---------------------------------------------------------------------------

describe('Property 8: Middleware redirige les non-admins hors de /admin', () => {
  it('redirects any non-admin role away from /admin paths', () => {
    // Feature: role-based-access-control, Property 8: Middleware redirige les non-admins hors de /admin
    fc.assert(
      fc.property(
        fc.constantFrom(...NON_ADMIN_ROLES),
        fc.constantFrom('/fr-TG/admin', '/fr-BJ/admin', '/en/admin'),
        (role, adminPath) => {
          const token = makeJwt(role);
          const decision = routingDecision(adminPath, token);
          return decision.type === 'redirect';
        },
      ),
      { numRuns: 100 },
    );
  });

  it('redirect destination is the locale root (not login)', () => {
    // Feature: role-based-access-control, Property 8: Middleware redirige les non-admins hors de /admin
    fc.assert(
      fc.property(
        fc.constantFrom(...NON_ADMIN_ROLES),
        fc.constantFrom('fr-TG', 'fr-BJ', 'en'),
        (role, locale) => {
          const token = makeJwt(role);
          const decision = routingDecision(`/${locale}/admin`, token);
          if (decision.type !== 'redirect') return false;
          return decision.to === `/${locale}`;
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Task 7.3 — Property 6: Requêtes non authentifiées redirigées vers login
// ---------------------------------------------------------------------------

describe('Property 6: Requêtes non authentifiées redirigées vers login', () => {
  it('redirects unauthenticated requests on protected paths to login', () => {
    // Feature: role-based-access-control, Property 6: Requêtes non authentifiées redirigées vers login
    fc.assert(
      fc.property(fc.constantFrom(...PROTECTED_PATHS), (path) => {
        const decision = routingDecision(path, undefined);
        return decision.type === 'redirect';
      }),
      { numRuns: 100 },
    );
  });

  it('redirect destination includes /login for unauthenticated requests', () => {
    // Feature: role-based-access-control, Property 6: Requêtes non authentifiées redirigées vers login
    fc.assert(
      fc.property(fc.constantFrom(...PROTECTED_PATHS), (path) => {
        const decision = routingDecision(path, undefined);
        if (decision.type !== 'redirect') return false;
        return decision.to.endsWith('/login');
      }),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Task 7.4 — Unit tests
// ---------------------------------------------------------------------------

describe('Unit tests: public QA paths', () => {
  it('lets /qa pass without a token', () => {
    const decision = routingDecision('/qa', undefined);
    expect(decision.type).toBe('pass');
  });

  it('lets /fr-TG/qa pass without a token', () => {
    const decision = routingDecision('/fr-TG/qa', undefined);
    expect(decision.type).toBe('pass');
  });
});

describe('Unit tests: admin access control', () => {
  it('allows admin role to access /fr-TG/admin without redirect', () => {
    const token = makeJwt('admin');
    const decision = routingDecision('/fr-TG/admin', token);
    expect(decision.type).toBe('pass');
  });

  it('redirects non-admin role away from /fr-TG/admin', () => {
    const token = makeJwt('medecin');
    const decision = routingDecision('/fr-TG/admin', token);
    expect(decision.type).toBe('redirect');
    if (decision.type === 'redirect') {
      expect(decision.to).toBe('/fr-TG');
    }
  });
});

describe('Unit tests: decodeRoleFromJwt', () => {
  it('extracts role from a valid JWT', () => {
    const token = makeJwt('admin');
    expect(decodeRoleFromJwt(token)).toBe('admin');
  });

  it('returns null for a malformed token', () => {
    expect(decodeRoleFromJwt('not.a.valid.jwt.at.all')).toBeNull();
    expect(decodeRoleFromJwt('onlyone')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Task 15.5 — i18n-medical-content: locale resolution tests
// Requirements: 6.2, 6.4, 6.5, 9.1
// ---------------------------------------------------------------------------

describe('resolveLocale — i18n-medical-content locale support', () => {
  it('returns fr-TG for fr-TG', () => {
    expect(resolveLocale('fr-TG')).toBe('fr-TG');
  });

  it('returns fr-BJ for fr-BJ', () => {
    expect(resolveLocale('fr-BJ')).toBe('fr-BJ');
  });

  it('returns en for en', () => {
    expect(resolveLocale('en')).toBe('en');
  });

  it('maps fr alias to fr-TG (backward compat, Requirement 9.1)', () => {
    expect(resolveLocale('fr')).toBe('fr-TG');
  });

  it('falls back to fr-TG for unsupported locales', () => {
    expect(resolveLocale('de')).toBe('fr-TG');
    expect(resolveLocale('es')).toBe('fr-TG');
    expect(resolveLocale('zh-CN')).toBe('fr-TG');
    expect(resolveLocale('')).toBe('fr-TG');
    expect(resolveLocale(null)).toBe('fr-TG');
    expect(resolveLocale(undefined)).toBe('fr-TG');
  });

  it('property: any unsupported locale resolves to fr-TG', () => {
    // Feature: i18n-medical-content, Property: unsupported locale fallback
    fc.assert(
      fc.property(
        fc.string().filter((s) => s !== 'fr-TG' && s !== 'fr-BJ' && s !== 'en' && s !== 'fr'),
        (unsupported) => resolveLocale(unsupported) === 'fr-TG',
      ),
      { numRuns: 100 },
    );
  });

  it('property: all supported locales resolve to themselves', () => {
    // Feature: i18n-medical-content, Property: supported locale identity
    fc.assert(
      fc.property(
        fc.constantFrom('fr-TG', 'fr-BJ', 'en'),
        (locale) => resolveLocale(locale) === locale,
      ),
      { numRuns: 100 },
    );
  });
});

describe('extractLocale — cookie override (Requirements 6.4, 6.5)', () => {
  it('cookie fr-BJ overrides pathname locale fr-TG', () => {
    const locale = extractLocale('/fr-TG/patients', 'fr-BJ');
    expect(locale).toBe('fr-BJ');
  });

  it('cookie fr-TG overrides pathname locale en', () => {
    const locale = extractLocale('/en/patients', 'fr-TG');
    expect(locale).toBe('fr-TG');
  });

  it('cookie fr alias resolves to fr-TG', () => {
    const locale = extractLocale('/en/patients', 'fr');
    expect(locale).toBe('fr-TG');
  });

  it('no cookie falls back to pathname locale', () => {
    expect(extractLocale('/fr-BJ/patients')).toBe('fr-BJ');
    expect(extractLocale('/en/patients')).toBe('en');
  });

  it('no cookie and no locale in pathname falls back to fr-TG', () => {
    expect(extractLocale('/patients')).toBe('fr-TG');
    expect(extractLocale('/')).toBe('fr-TG');
  });
});

describe('routingDecision — new locale paths', () => {
  it('unauthenticated user on /fr-BJ/diagnose redirects to /fr-BJ/login', () => {
    const decision = routingDecision('/fr-BJ/diagnose', undefined);
    expect(decision.type).toBe('redirect');
    if (decision.type === 'redirect') {
      expect(decision.to).toBe('/fr-BJ/login');
    }
  });

  it('unauthenticated user on /en/patients redirects to /en/login', () => {
    const decision = routingDecision('/en/patients', undefined);
    expect(decision.type).toBe('redirect');
    if (decision.type === 'redirect') {
      expect(decision.to).toBe('/en/login');
    }
  });

  it('authenticated user on /fr-TG/patients passes through', () => {
    const token = makeJwt('medecin');
    const decision = routingDecision('/fr-TG/patients', token);
    expect(decision.type).toBe('pass');
  });

  it('cookie locale overrides path locale in redirect destination', () => {
    const decision = routingDecision('/fr-TG/diagnose', undefined, 'fr-BJ');
    expect(decision.type).toBe('redirect');
    if (decision.type === 'redirect') {
      expect(decision.to).toBe('/fr-BJ/login');
    }
  });
});
