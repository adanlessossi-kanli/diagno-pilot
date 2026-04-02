import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  resolve: {
    alias: {
      '@diagno-pilot/types': path.resolve(__dirname, '../types/index.ts'),
    },
  },
  test: {
    globals: true,
  },
});
