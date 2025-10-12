import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      lines: 80,
      exclude: ['**/*.test.ts', '**/__tests__/**', '**/index.ts'],
    },
    include: ['**/*.test.ts'],
  },
});
