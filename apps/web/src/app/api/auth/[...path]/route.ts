import { NextRequest, NextResponse } from 'next/server';

/**
 * Auth proxy — forwards /api/auth/* requests to the FastAPI backend and
 * relays Set-Cookie headers back to the browser.
 *
 * This is required because Next.js rewrites() do not forward Set-Cookie
 * headers from the upstream to the browser. By using a Route Handler we
 * can explicitly relay them so cookies are set on the Next.js origin
 * (same-origin as the frontend).
 *
 * Routes handled:
 *   POST /api/auth/login   → POST {BACKEND}/api/v1/auth/login
 *   POST /api/auth/refresh → POST {BACKEND}/api/v1/auth/refresh
 *   POST /api/auth/logout  → POST {BACKEND}/api/v1/auth/logout
 *   GET  /api/auth/me      → GET  {BACKEND}/api/v1/auth/me
 */

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? 'http://localhost:8000';

async function proxyToBackend(request: NextRequest, path: string[]): Promise<NextResponse> {
  const backendPath = `/api/v1/auth/${path.join('/')}`;
  const url = `${BACKEND}${backendPath}`;

  // Forward cookies from the browser to the backend
  const cookieHeader = request.headers.get('cookie') ?? '';

  const init: RequestInit = {
    method: request.method,
    headers: {
      'content-type': request.headers.get('content-type') ?? 'application/json',
      ...(cookieHeader ? { cookie: cookieHeader } : {}),
      ...(request.headers.get('x-csrf-token')
        ? { 'x-csrf-token': request.headers.get('x-csrf-token')! }
        : {}),
    },
  };

  if (request.method !== 'GET' && request.method !== 'HEAD') {
    init.body = await request.text();
  }

  let backendResp: Response;
  try {
    backendResp = await fetch(url, init);
  } catch (err) {
    console.error(`[auth-proxy] Failed to reach backend at ${url}:`, err);
    return NextResponse.json(
      { detail: 'Backend unavailable' },
      { status: 503 },
    );
  }

  const contentType = backendResp.headers.get('content-type') ?? '';
  const body = contentType.includes('application/json')
    ? await backendResp.json().catch(() => ({}))
    : await backendResp.text().catch(() => '');

  const response = NextResponse.json(body, { status: backendResp.status });

  // Relay Set-Cookie headers so the browser receives them on the Next.js origin
  backendResp.headers.forEach((value, key) => {
    if (key.toLowerCase() === 'set-cookie') {
      response.headers.append('set-cookie', value);
    }
  });

  return response;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await params;
  return proxyToBackend(request, path);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await params;
  return proxyToBackend(request, path);
}
