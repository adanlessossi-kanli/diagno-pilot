import type { NextConfig } from 'next';
import createNextIntlPlugin from 'next-intl/plugin';
import path from 'path';

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');

// Resolve monorepo root regardless of where Next.js is invoked from
const monorepoRoot = path.resolve(__dirname, '../..');

const isDev = process.env.NODE_ENV !== 'production';

// In development, Next.js HMR requires 'unsafe-inline' and 'unsafe-eval' for
// React Fast Refresh. In production these are removed for strict XSS protection.
const scriptSrc = isDev ? "'self' 'unsafe-inline' 'unsafe-eval'" : "'self'";

// API is proxied through Next.js rewrites so all requests go to 'self' —
// no cross-origin cookie issues. connect-src 'self' is sufficient.
const connectSrc = "'self'";

// Internal URL used by Next.js server-side rewrites (inside Docker: service name;
// outside Docker / local dev: localhost:8000).
const backendInternalUrl = process.env.BACKEND_INTERNAL_URL ?? 'http://localhost:8000';

const nextConfig: NextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  // Increase proxy timeout for long-running requests (document upload + embedding)
  experimental: {
    proxyTimeout: 300_000, // 5 minutes
  },
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: `default-src 'self'; script-src ${scriptSrc}; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://images.unsplash.com; connect-src ${connectSrc}; font-src 'self'; frame-ancestors 'none';`,
          },
        ],
      },
    ];
  },
  // Proxy /api/v1/* through Next.js so cookies stay same-origin (localhost:3000).
  // BACKEND_INTERNAL_URL is the Docker service name URL; falls back to localhost for local dev.
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: `${backendInternalUrl}/api/v1/:path*`,
      },
    ];
  },
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'images.unsplash.com',
        pathname: '/**',
      },
    ],
  },
  transpilePackages: [
    '@diagno-pilot/types',
    '@diagno-pilot/api-client',
    '@diagno-pilot/ui',
    '@diagno-pilot/i18n',
  ],
  webpack(config) {
    // Hard-wire workspace package paths so webpack never relies on symlinks
    config.resolve.alias = {
      ...config.resolve.alias,
      '@diagno-pilot/types': path.join(monorepoRoot, 'packages/types/index.ts'),
      '@diagno-pilot/api-client': path.join(monorepoRoot, 'packages/api-client/index.ts'),
      '@diagno-pilot/ui': path.join(monorepoRoot, 'packages/ui/index.ts'),
      '@diagno-pilot/i18n': path.join(monorepoRoot, 'packages/i18n/index.ts'),
    };
    return config;
  },
};

export default withNextIntl(nextConfig);
