import { expect, test } from '@playwright/test'

/**
 * End-to-end smoke tests against a running stack.
 *
 *   cd frontend
 *   npx playwright install chromium      # once
 *   npm run dev                          # Vite on :5173
 *   # API on :8000 with the demo data loaded (python scripts/bootstrap_demo.py)
 *   npm run test:e2e
 */

const FRONTEND = process.env.E2E_FRONTEND ?? 'http://127.0.0.1:5173'
const API = process.env.E2E_API ?? 'http://127.0.0.1:8000'

test.describe('NPI Launch Risk Digital Twin', () => {
  test.beforeEach(async ({ page }) => {
    const errors: string[] = []
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text())
    })
    ;(page as unknown as { __errors: string[] }).__errors = errors
    await page.goto(FRONTEND, { waitUntil: 'domcontentloaded' })
  })

  test('command centre lists the demo programs', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /launch risk is concentrating/i })).toBeVisible()
    await expect(page.locator('.program-card').first()).toBeVisible()
    const programs = await page.locator('.program-card').count()
    expect(programs).toBeGreaterThan(0)
  })

  test('program workspace exposes the schedule view', async ({ page }) => {
    await page.locator('.program-card').first().click()
    await expect(page).toHaveURL(/\/projects\/.+\/overview/)
    await page.getByRole('link', { name: 'Schedule & capacity' }).click()
    await expect(page).toHaveURL(/\/schedule/)
    await expect(page.locator('.chart-wrap')).toBeVisible()
  })

  test('monte carlo view shows a distribution and convergence', async ({ page }) => {
    await page.locator('.program-card').first().click()
    await page.getByRole('link', { name: 'Monte Carlo' }).click()
    await expect(page.locator('.kpi-grid').first()).toBeVisible()
    await expect(page.getByText(/Convergence/i)).toBeVisible()
  })

  test('scenario comparison produces a paired delta', async ({ page }) => {
    test.slow()
    await page.locator('.program-card').first().click()
    await page.getByRole('link', { name: 'Scenarios' }).click()
    await expect(page.locator('.scenario-card').first()).toBeVisible()
    const scenario = page.locator('.scenario-card', { hasText: 'Schedule acceleration' })
    if (await scenario.count()) {
      await scenario.first().click()
      await page.getByRole('button', { name: 'Simulate paired comparison' }).click()
      await expect(page.getByText(/Paired difference/i)).toBeVisible({ timeout: 120_000 })
    }
  })

  test('the copilot answers with citations', async ({ page }) => {
    test.slow()
    await page.locator('.program-card').first().click()
    await page.getByRole('link', { name: 'Risk copilot' }).click()
    await expect(page.locator('.suggestion').first()).toBeVisible()
    await page.locator('textarea').fill('What is the on-time probability for this program?')
    await page.getByRole('button', { name: 'Ask' }).click()
    await expect(page.locator('.citation').first()).toBeVisible({ timeout: 180_000 })
  })

  test('no console errors are produced while browsing', async ({ page }) => {
    await page.locator('.program-card').first().click()
    await page.getByRole('link', { name: 'Methodology' }).click()
    await expect(page.locator('.method-grid')).toBeVisible()
    const errors = (page as unknown as { __errors: string[] }).__errors ?? []
    expect(errors).toEqual([])
  })
})

test.describe('API', () => {
  test('health and readiness respond', async ({ request }) => {
    const health = await request.get(`${API}/api/health`)
    expect(health.ok()).toBeTruthy()
    expect((await health.json()).status).toBe('ok')

    const ready = await request.get(`${API}/api/ready`)
    expect(ready.ok()).toBeTruthy()
  })

  test('projects are listed and schedules are computed', async ({ request }) => {
    const projects = await (await request.get(`${API}/api/projects`)).json()
    expect(projects.length).toBeGreaterThan(0)
    const id = projects[0].id
    const schedule = await (await request.get(`${API}/api/projects/${id}/schedule?mode=both`)).json()
    expect(schedule.cpm.project_duration).toBeGreaterThan(0)
    expect(schedule.constrained.makespan).toBeGreaterThanOrEqual(schedule.cpm.project_duration)
  })
})
