import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    globals: true,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@diagno-pilot/types': path.resolve(__dirname, '../../packages/types/index.ts'),
      '@diagno-pilot/api-client': path.resolve(__dirname, '../../packages/api-client/index.ts'),
      '@diagno-pilot/i18n': path.resolve(__dirname, '../../packages/i18n/index.ts'),
    },
  },
});
