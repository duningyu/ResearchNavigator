import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 90_000,
  retries: 1,
  use: {
    baseURL: process.env.RN_E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    channel: process.env.RN_E2E_BROWSER_CHANNEL || undefined,
    trace: 'retain-on-failure',
    animations: 'disabled',
  },
});
