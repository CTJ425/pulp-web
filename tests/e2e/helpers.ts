import { request, type APIRequestContext } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const BASE = process.env.E2E_BASE_URL ?? 'http://localhost:8080'

function adminPassword(): string {
  const envFile = resolve(
    dirname(fileURLToPath(import.meta.url)),
    '../../deploy/compose/.env',
  )
  const match = readFileSync(envFile, 'utf8').match(/^PULP_ADMIN_PASSWORD=(.+)$/m)
  if (!match) throw new Error('PULP_ADMIN_PASSWORD not found in deploy/compose/.env')
  return match[1]
}

/** 直接打 Pulp API 清掉 e2e 測試留下的 repo,讓建立流程可重複執行。 */
export async function deleteRepoIfExists(name: string): Promise<void> {
  const ctx: APIRequestContext = await request.newContext({
    baseURL: BASE,
    httpCredentials: { username: 'admin', password: adminPassword() },
  })
  try {
    for (const kind of ['distributions', 'repositories', 'remotes']) {
      const list = await ctx.get(`/pulp/api/v3/${kind}/rpm/rpm/?name=${name}`)
      if (!list.ok()) continue
      for (const item of (await list.json()).results ?? []) {
        const del = await ctx.delete(item.pulp_href)
        if (del.status() === 202) {
          const { task } = await del.json()
          await waitPulpTask(ctx, task)
        }
      }
    }
  } finally {
    await ctx.dispose()
  }
}

async function waitPulpTask(ctx: APIRequestContext, href: string): Promise<void> {
  for (let i = 0; i < 60; i++) {
    const task = await (await ctx.get(href)).json()
    if (['completed', 'failed', 'canceled'].includes(task.state)) return
    await new Promise((r) => setTimeout(r, 1000))
  }
  throw new Error(`pulp task ${href} 未在時限內結束`)
}
