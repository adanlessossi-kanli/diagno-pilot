import type { NextConfig } from 'next';
import createNextIntlPlugin from 'next-intl/plugin';
import path from 'path';

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');

// Resolve monorepo root regardless of where Next.js is invoked from
const monorepoRoot = path.resolve(__dirname, '../..');

const nextConfig: NextConfig = {
  reactStrictMode: true,
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
