import createMiddleware from 'next-intl/middleware';
import { NextRequest, NextResponse } from 'next/server';
import { routing } from './i18n/routing';

const intlMiddleware = createMiddleware(routing);

/**
 * Decodes the role from a JWT token without signature verification.
 * Reads the payload (second segment) and extracts the `role` field.
 */
function decodeRoleFromJwt(token: string): string | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    // Base64url → Base64 → decode
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const decoded = JSON.parse(atob(payload));
    return typeof decoded.role === 'string' ? decoded.role : null;
  } catch {
    return null;
  }
}

/** Public paths that never require authentication */
const PUBLIC_PATHS = ['/login', '/qa'];

function isPublicPath(pathname: string): boolean {
  // Allow /qa and /[locale]/qa
  if (pathname === '/qa') return true;
  // Allow /[locale]/login and /[locale]/qa
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length >= 2) {
    const afterLocale = '/' + segments.slice(1).join('/');
    if (PUBLIC_PATHS.some((p) => afterLocale === p || afterLocale.startsWith(p + '/'))) {
      return true;
    }
  }
  // Allow bare /login (no locale prefix)
  if (pathname === '/login') return true;
  return false;
}

function isQaPath(pathname: string): boolean {
  if (pathname === '/qa') return true;
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length >= 2 && segments[1] === 'qa') return true;
  return false;
}

/** Extract the locale prefix from the pathname, defaulting to the default locale */
function extractLocale(pathname: string): string {
  const segments = pathname.split('/').filter(Boolean);
  const supportedLocales = routing.locales as readonly string[];
  if (segments.length > 0 && supportedLocales.includes(segments[0])) {
    return segments[0];
  }
  return routing.defaultLocale;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Always let public paths through (login, qa)
  if (isPublicPath(pathname)) {
    return intlMiddleware(request);
  }

  const token = request.cookies.get('access_token')?.value;
  const role = token ? decodeRoleFromJwt(token) : null;
  const locale = extractLocale(pathname);

  // Protect /[locale]/admin — redirect non-admins to home
  if (pathname.includes('/admin') && role !== 'admin') {
    return NextResponse.redirect(new URL(`/${locale}`, request.url));
  }

  // Redirect unauthenticated users to login (QA paths already handled above)
  if (!token && !isQaPath(pathname)) {
    return NextResponse.redirect(new URL(`/${locale}/login`, request.url));
  }

  return intlMiddleware(request);
}

export const config = {
  // Match all pathnames except static files, api routes, and Next.js internals
  matcher: ['/((?!api|_next|_vercel|.*\\..*).*)'],
};
