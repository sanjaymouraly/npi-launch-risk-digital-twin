import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end configuration. The suite expects a running API (:8000) and a running
 * Vite dev server (:5173) with the demo data loaded:
 *
 *   python scripts/bootstrap_demo.py
 *   cd backend && uvicorn app.main:app --port 8000
 *   cd frontend && npm run dev
 */
export default defineConfig({
  testDir: './tests',
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_FRONTEND ?? 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    viewport: { width: 1600, height: 1000 },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
