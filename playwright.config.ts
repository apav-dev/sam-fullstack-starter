import { defineConfig } from '@playwright/test'

// Smoke tests run against a live deployment (deploy.sh sets E2E_BASE_URL)
// or a local dev stack (default http://localhost:5173).
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  retries: 1,
  use: {
    baseURL: process.env['E2E_BASE_URL'] ?? 'http://localhost:5173',
    screenshot: 'only-on-failure',
  },
  reporter: [['list']],
})
