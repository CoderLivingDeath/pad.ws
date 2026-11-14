import { defineConfig } from 'vitest/config';
import path from 'node:path';

// Frontend unit and hook tests. Browser journeys stay in tests/e2e (Playwright).
export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'text-summary', 'json-summary', 'html'],
      reportsDirectory: '../../coverage/frontend',
      // Only the modules with real unit coverage are gated here. Editor,
      // canvas and Coder UI modules depend on Excalidraw/Monaco internals and
      // are exercised through the Playwright Use Cases (UC-02…UC-05).
      include: [
        'src/lib/authRefreshManager.ts',
        'src/lib/debounce.ts',
        'src/hooks/useLogout.ts',
        'src/hooks/useWorkspace.ts',
        'src/hooks/useCallbackRefState.ts',
      ],
      exclude: ['src/**/*.test.{ts,tsx}', 'src/test/**'],
      thresholds: {
        statements: 70,
        lines: 70,
        branches: 60,
        functions: 70,
      },
    },
  },
});
