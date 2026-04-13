export function HEAD() {
  return new Response(null, { status: 200 });
}

export function GET() {
  return Response.json({ status: 'ok' });
}
