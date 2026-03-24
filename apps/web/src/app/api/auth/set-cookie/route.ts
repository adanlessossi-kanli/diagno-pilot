import { NextRequest, NextResponse } from 'next/server';

const COOKIE_NAME = 'auth_token';
const IS_PRODUCTION = process.env.NODE_ENV === 'production';

/**
 * POST /api/auth/set-cookie
 * Body: { token: string }
 * Sets the JWT as an httpOnly cookie.
 */
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  const token: unknown = body?.token;

  if (!token || typeof token !== 'string') {
    return NextResponse.json({ error: 'Missing token' }, { status: 400 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: IS_PRODUCTION,
    sameSite: 'strict',
    path: '/',
    // 8 hours — matches typical JWT expiry
    maxAge: 60 * 60 * 8,
  });

  return response;
}

/**
 * DELETE /api/auth/set-cookie
 * Clears the auth_token cookie.
 */
export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(COOKIE_NAME, '', {
    httpOnly: true,
    secure: IS_PRODUCTION,
    sameSite: 'strict',
    path: '/',
    maxAge: 0,
  });

  return response;
}
