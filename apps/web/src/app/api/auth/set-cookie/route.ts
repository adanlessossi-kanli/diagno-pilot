import { NextRequest, NextResponse } from 'next/server';

/**
 * POST /api/auth/set-cookie
 * Proxy endpoint: forwards login credentials to the backend and relays
 * the httpOnly auth cookies back to the browser.
 *
 * This is needed because the backend runs on a different origin in
 * development, so the browser cannot receive httpOnly cookies directly.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? '';

  const body = await request.text();
  const backendResp = await fetch(`${apiBase}/api/v1/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': request.headers.get('content-type') ?? 'application/x-www-form-urlencoded',
    },
    body,
  });

  const data = await backendResp.json().catch(() => ({}));
  const response = NextResponse.json(data, { status: backendResp.status });

  // Relay Set-Cookie headers from the backend to the browser
  backendResp.headers.forEach((value, key) => {
    if (key.toLowerCase() === 'set-cookie') {
      response.headers.append('set-cookie', value);
    }
  });

  return response;
}
