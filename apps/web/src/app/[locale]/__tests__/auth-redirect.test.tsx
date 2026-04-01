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

const PROTECTED_PATHS = [
  '/fr/patients',
  '/fr/diagnose',
  '/fr/chat',
  '/fr/admin',
  '/en/patients',
  '/en/diagnose',
  '/en/chat',
  '/en/admin',
] as const;

const NON_ADMIN_ROLES = ['medecin', 'pharmacien', 'infirmiere', 'guest', 'user'] as const;

// ---------------------------------------------------------------------------
// Property 12: Unauthenticated web requests redirected to login
// Validates: Requirements 7.9
// ---------------------------------------------------------------------------

describe('Property 12: Unauthenticated web requests redirected to login', () => {
  // Feature: testing-coverage, Property 12: Unauthenticated web requests redirected to login
  it('redirects any protected route without a session token to login', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...PROTECTED_PATHS),
        (path) => {
          const decision = routingDecision(path, undefined);
          // Admin paths without token redirect to locale root (not login),
          // but all other protected paths redirect to login
          if (path.includes('/admin')) {
            return decision.type === 'redirect';
          }
          return decision.type === 'redirect' && decision.to.endsWith('/login');
        },
      ),
      { numRuns: 100 },
    );
  });

  it('redirect destination is /{locale}/login for non-admin protected paths', () => {
    // Feature: testing-coverage, Property 12: Unauthenticated web requests redirected to login
    fc.assert(
      fc.property(
        fc.constantFrom('fr', 'en'),
        fc.constantFrom('patients', 'diagnose', 'chat'),
        (locale, page) => {
          const path = `/${locale}/${page}`;
          const decision = routingDecision(path, undefined);
          if (decision.type !== 'redirect') return false;
          return decision.to === `/${locale}/login`;
        },
      ),
      { numRuns: 100 },
    );
  });

  it('does not redirect authenticated users on protected paths', () => {
    // Feature: testing-coverage, Property 12: Unauthenticated web requests redirected to login
    fc.assert(
      fc.property(
        fc.constantFrom('fr', 'en'),
        fc.constantFrom('patients', 'diagnose', 'chat'),
        (locale, page) => {
          const path = `/${locale}/${page}`;
          const token = makeJwt('medecin');
          const decision = routingDecision(path, token);
          return decision.type === 'pass';
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 13: Non-admin users see access-denied on admin pages
// Validates: Requirements 7.10
// ---------------------------------------------------------------------------

describe('Property 13: Non-admin users see access-denied on admin pages', () => {
  // Feature: testing-coverage, Property 13: Non-admin users see access-denied on admin pages
  it('redirects any non-admin role away from admin paths', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...NON_ADMIN_ROLES),
        fc.constantFrom('fr', 'en'),
        (role, locale) => {
          const token = makeJwt(role);
          const decision = routingDecision(`/${locale}/admin`, token);
          return decision.type === 'redirect';
        },
      ),
      { numRuns: 100 },
    );
  });

  it('admin role is allowed through admin paths', () => {
    // Feature: testing-coverage, Property 13: Non-admin users see access-denied on admin pages
    fc.assert(
      fc.property(
        fc.constantFrom('fr', 'en'),
        (locale) => {
          const token = makeJwt('admin');
          const decision = routingDecision(`/${locale}/admin`, token);
          return decision.type === 'pass';
        },
      ),
      { numRuns: 100 },
    );
  });

  it('non-admin redirect destination is the locale root (not login)', () => {
    // Feature: testing-coverage, Property 13: Non-admin users see access-denied on admin pages
    fc.assert(
      fc.property(
        fc.constantFrom(...NON_ADMIN_ROLES),
        fc.constantFrom('fr', 'en'),
        (role, locale) => {
          const token = makeJwt(role);
          const decision = routingDecision(`/${locale}/admin`, token);
          if (decision.type !== 'redirect') return false;
          // Redirected to locale root, not to login
          return decision.to === `/${locale}`;
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Unit tests: example-based redirect scenarios
// ---------------------------------------------------------------------------

describe('Unit tests: unauthenticated redirect to login', () => {
  it('redirects /fr/patients without token to /fr/login', () => {
    const decision = routingDecision('/fr/patients', undefined);
    expect(decision.type).toBe('redirect');
    if (decision.type === 'redirect') {
      expect(decision.to).toBe('/fr/login');
    }
  });

  it('redirects /en/diagnose without token to /en/login', () => {
    const decision = routingDecision('/en/diagnose', undefined);
    expect(decision.type).toBe('redirect');
    if (decision.type === 'redirect') {
      expect(decision.to).toBe('/en/login');
    }
  });

  it('redirects /fr/chat without token to /fr/login', () => {
    const decision = routingDecision('/fr/chat', undefined);
    expect(decision.type).toBe('redirect');
    if (decision.type === 'redirect') {
      expect(decision.to).toBe('/fr/login');
    }
  });

  it('allows /fr/login without token (public path)', () => {
    const decision = routingDecision('/fr/login', undefined);
    expect(decision.type).toBe('pass');
  });

  it('allows /fr/qa without token (public path)', () => {
    const decision = routingDecision('/fr/qa', undefined);
    expect(decision.type).toBe('pass');
  });
});

describe('Unit tests: admin access-denied for non-admin roles', () => {
  it('redirects medecin from /fr/admin to /fr', () => {
    const token = makeJwt('medecin');
    const decision = routingDecision('/fr/admin', token);
    expect(decision.type).toBe('redirect');
    if (decision.type === 'redirect') {
      expect(decision.to).toBe('/fr');
    }
  });

  it('redirects pharmacien from /en/admin to /en', () => {
    const token = makeJwt('pharmacien');
    const decision = routingDecision('/en/admin', token);
    expect(decision.type).toBe('redirect');
    if (decision.type === 'redirect') {
      expect(decision.to).toBe('/en');
    }
  });

  it('allows admin role through /fr/admin', () => {
    const token = makeJwt('admin');
    const decision = routingDecision('/fr/admin', token);
    expect(decision.type).toBe('pass');
  });

  it('redirects unauthenticated user from /fr/admin (no token)', () => {
    const decision = routingDecision('/fr/admin', undefined);
    expect(decision.type).toBe('redirect');
  });
});
