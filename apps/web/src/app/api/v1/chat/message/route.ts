/**
 * Streaming proxy for POST /api/v1/chat/message
 *
 * Next.js rewrites may buffer SSE responses. This route handler
 * explicitly streams the backend SSE response through to the client,
 * preserving the text/event-stream content type.
 */
import { NextRequest } from 'next/server';

// Use Node.js runtime — edge runtime cannot access Docker-internal URLs at runtime
export const runtime = 'nodejs';
// Disable static generation — this is a dynamic streaming endpoint
export const dynamic = 'force-dynamic';

const backendUrl = process.env.BACKEND_INTERNAL_URL ?? 'http://localhost:8000';

export async function POST(request: NextRequest) {
  const body = await request.text();

  // Forward all relevant headers (auth cookies, CSRF, content-type, locale)
  const forwardHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const cookie = request.headers.get('cookie');
  if (cookie) forwardHeaders['Cookie'] = cookie;
  const csrf = request.headers.get('x-csrf-token');
  if (csrf) forwardHeaders['X-CSRF-Token'] = csrf;
  const acceptLang = request.headers.get('accept-language');
  if (acceptLang) forwardHeaders['Accept-Language'] = acceptLang;

  const backendRes = await fetch(`${backendUrl}/api/v1/chat/message`, {
    method: 'POST',
    headers: forwardHeaders,
    body,
  });

  // If the backend returned an error (non-2xx), forward it as-is
  if (!backendRes.ok) {
    const errorBody = await backendRes.text();
    return new Response(errorBody, {
      status: backendRes.status,
      headers: { 'Content-Type': backendRes.headers.get('Content-Type') ?? 'application/json' },
    });
  }

  // Stream the SSE response through without buffering
  return new Response(backendRes.body, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}
