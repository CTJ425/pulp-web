import { expect, test, type Page } from '@playwright/test'
import { deleteRepoIfExists } from '../helpers'

// 前置:make dev && make seed(tiny-rpm / tiny-deb / tiny-hello)

/** 以名稱欄精確比對列;hasText 會誤中上游 URL 內含相同字串的其他列 */
function repoRow(page: Page, name: string) {
  return page
    .locator('tbody tr')
    .filter({ has: page.locator('strong', { hasText: new RegExp(`^${name}$`) }) })
}

test.describe('Dashboard', () => {
  test('顯示系統總覽卡片與元件版本', async ({ page }) => {
    await page.goto('/dashboard')
    const repoCard = page.locator('.card', { hasText: 'Repositories' })
    await expect(repoCard.locator('.card-value')).not.toHaveText('0')
    await expect(page.locator('.card', { hasText: 'Workers' })).toContainText('/')
    // 元件版本表要列出 pulp 插件
    await expect(page.locator('table')).toContainText('core')
    await expect(page.locator('table')).toContainText('rpm')
  })
})

test.describe('Repositories', () => {
  test('列出 seed 的三種 repo,可過濾型態', async ({ page }) => {
    await page.goto('/repos')
    for (const name of ['tiny-rpm', 'tiny-deb', 'tiny-hello']) {
      await expect(repoRow(page, name)).toBeVisible()
    }
    await page.getByRole('button', { name: 'rpm', exact: true }).click()
    await expect(repoRow(page, 'tiny-rpm')).toBeVisible()
    await expect(repoRow(page, 'tiny-deb')).toHaveCount(0)
  })

  test('Sync now 觸發同步並回到可再同步狀態', async ({ page }) => {
    await page.goto('/repos')
    const row = repoRow(page, 'tiny-rpm')
    await row.getByRole('button', { name: 'Sync now' }).click()
    // 202 後徽章出現(running/waiting),完成後徽章消失、按鈕回來
    await expect(row.locator('.badge')).toBeVisible()
    await expect(row.getByRole('button', { name: 'Sync now' })).toBeVisible({ timeout: 60_000 })
    // 不應出現失敗橫幅
    await expect(page.locator('.banner-err')).toHaveCount(0)
  })

  test('Client config 顯示可複製的設定片段', async ({ page }) => {
    await page.goto('/repos')
    const row = repoRow(page, 'tiny-rpm')
    await row.getByRole('button', { name: 'Client config' }).click()
    await expect(page.locator('.config-pre')).toContainText('baseurl=')
    await expect(page.locator('.config-pre')).toContainText('/pulp/content/tiny-rpm/')
    await page.getByRole('button', { name: '關閉' }).click()
  })

  test('新增 repo 精靈:建立 rpm repo 並完成', async ({ page }) => {
    await deleteRepoIfExists('e2e-rpm')
    await page.goto('/repos')
    await page.getByRole('button', { name: '+ 新增 Repo' }).click()
    await page.getByLabel('名稱', { exact: true }).fill('e2e-rpm')
    await page.getByLabel('上游 URL', { exact: true }).fill('http://fixtures/tiny-rpm/')
    await page.getByRole('button', { name: '建立' }).click()
    // 建立成功 → modal 關閉,列表出現新 repo(distribution task 完成後)
    await expect(page.locator('.modal')).toHaveCount(0)
    const row = repoRow(page, 'e2e-rpm')
    await expect(row).toBeVisible({ timeout: 30_000 })
    // 徽章(建立 task)結束後 Sync now 可用,且無錯誤橫幅
    await expect(row.getByRole('button', { name: 'Sync now' })).toBeVisible({ timeout: 60_000 })
    await expect(page.locator('.banner-err')).toHaveCount(0)
  })

  test('新增重複名稱顯示 409 錯誤', async ({ page }) => {
    await page.goto('/repos')
    await page.getByRole('button', { name: '+ 新增 Repo' }).click()
    await page.getByLabel('名稱', { exact: true }).fill('tiny-rpm')
    await page.getByLabel('上游 URL', { exact: true }).fill('http://fixtures/tiny-rpm/')
    await page.getByRole('button', { name: '建立' }).click()
    await expect(page.locator('.modal .banner-err')).toContainText('已存在')
  })
})

test.describe('Tasks', () => {
  test('列出任務並可依狀態過濾', async ({ page }) => {
    await page.goto('/tasks')
    await expect(page.locator('.table tbody tr').first()).toBeVisible()
    await page.getByRole('button', { name: 'completed' }).click()
    const badges = page.locator('.table .badge')
    await expect(badges.first()).toBeVisible()
    for (const text of await badges.allTextContents()) {
      expect(text).toBe('completed')
    }
  })
})
