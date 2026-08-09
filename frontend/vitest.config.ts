import { defineConfig } from 'vitest/config'

/**
 * Deliberately separate from vite.config.ts.
 *
 * Vitest 2 bundles its own older Vite, so importing `defineConfig` from
 * `vitest/config` into the app config makes the two Vite type trees collide and
 * `tsc -b` fails on `server.proxy`. Keeping the test config in its own file
 * leaves the build typed against the real Vite and costs nothing — these tests
 * cover plain modules and need no plugins.
 */
export default defineConfig({
  test: {
    // The api client talks to localStorage, which needs a DOM.
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
  },
})
