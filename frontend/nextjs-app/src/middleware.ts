import { NextRequest, NextResponse } from 'next/server';

// Simple dev-time proxy to API Gateway when running locally.
// Set NEXT_PUBLIC_API_BASE to your deployed API base URL.
export function middleware(req: NextRequest) {
  const url = new URL(req.url);
  const base = process.env.NEXT_PUBLIC_API_BASE;
  if (!base) return NextResponse.next();

  if (url.pathname.startsWith('/api/')) {
    const target = base.replace(/\/$/, '') + url.pathname.replace(/^\/api\//, '/');
    const proxied = new URL(target + (url.search || ''));
    const requestHeaders = new Headers(req.headers);
    requestHeaders.delete('host');
    return fetch(proxied, {
      method: req.method,
      headers: requestHeaders,
      body: req.body as any,
    }).then(r => new NextResponse(r.body, { status: r.status, headers: r.headers }));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ['/api/:path*'],
};
