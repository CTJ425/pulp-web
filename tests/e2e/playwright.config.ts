import { defineConfig } from '@playwright/test'

// 打 dev 環境(make dev && make seed 之後執行)
export default defineConfig({
  testDir: './specs',
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8080',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
})
