import { expect, test } from '@playwright/test'

// Post-deploy smoke test: the SPA loads, auth works, the home page renders.
//
// With E2E_EMAIL/E2E_PASSWORD set: logs in with that account.
// Without: signs up a fresh throwaway user (fine on test envs; set credentials
// for prod if signups are domain-restricted).
test('app loads and auth works', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/login/)

  const email = process.env['E2E_EMAIL']
  const password = process.env['E2E_PASSWORD']

  if (email && password) {
    await page.getByPlaceholder('Email').fill(email)
    await page.getByPlaceholder('Password', { exact: true }).fill(password)
    await page.getByRole('button', { name: 'Sign in' }).click()
  } else {
    await page.getByRole('link', { name: 'Create one' }).click()
    await page.getByPlaceholder('Name').fill('Smoke Test')
    await page.getByPlaceholder('Email').fill(`smoke-${Date.now()}@example.com`)
    await page.getByPlaceholder('Password (min 8 characters)').fill('smoketest-pw-1')
    await page.getByRole('button', { name: 'Create account' }).click()
  }

  // Landed on the authed home page
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('Async job demo', { exact: false })).toBeVisible()
})
