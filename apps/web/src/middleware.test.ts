import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';

// ---------------------------------------------------------------------------
// Inline helpers mirroring middleware logic (no Next.js runtime needed)
// ---------------------------------------------------------------------------

const SUPPORTED_LOCALES = ['fr', 'en'] as const;
const DEFAULT_LOCALE = 'fr';
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

function extractLocale(pathname: string): string {
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length > 0 && (SUPPORTED_LOCALES as readonly string[]).includes(segments[0])) {
    return segments[0];
  }
  return DEFAULT_LOCALE;
}

type Decision = { type: 'pass' } | { type: 'redirect'; to: string };

function routingDecision(pathname: string, token: string | undefined): Decision {
  if (isPublicPath(pathname)) return { type: 'pass' };
  const role = token ? decodeRoleFromJwt(token) : null;
  const locale = extractLocale(pathname);
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
  '/fr/patients',
  '/fr/diagnose',
  '/fr/chat',
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
        fc.constantFrom('/fr/admin', '/en/admin'),
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
        fc.constantFrom('fr', 'en'),
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

  it('lets /fr/qa pass without a token', () => {
    const decision = routingDecision('/fr/qa', undefined);
    expect(decision.type).toBe('pass');
  });
});

describe('Unit tests: admin access control', () => {
  it('allows admin role to access /fr/admin without redirect', () => {
    const token = makeJwt('admin');
    const decision = routingDecision('/fr/admin', token);
    expect(decision.type).toBe('pass');
  });

  it('redirects non-admin role away from /fr/admin', () => {
    const token = makeJwt('medecin');
    const decision = routingDecision('/fr/admin', token);
    expect(decision.type).toBe('redirect');
    if (decision.type === 'redirect') {
      expect(decision.to).toBe('/fr');
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
