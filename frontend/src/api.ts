import type { Overview, Repo, RepoCreate, RepoType, Task } from './types'

// API base URL 於 runtime 注入(容器 entrypoint 產生 /config.js);dev 走 vite proxy
declare global {
  interface Window {
    __CONFIG__?: { apiBase?: string }
  }
}
const API_BASE = (window.__CONFIG__?.apiBase ?? '/api') + '/v1'

export class ApiError extends Error {
  status: number
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(API_BASE + path, {
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  })
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const body = await resp.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* 非 JSON 錯誤內容,保留 statusText */
    }
    throw new ApiError(resp.status, detail)
  }
  const text = await resp.text()
  return (resp.headers.get('content-type')?.includes('application/json')
    ? JSON.parse(text)
    : text) as T
}

export const api = {
  overview: () => request<Overview>('/system/overview'),
  repos: (type?: RepoType) => request<Repo[]>(`/repos${type ? `?type=${type}` : ''}`),
  createRepo: (body: RepoCreate) =>
    request<{ task: string }>('/repos', { method: 'POST', body: JSON.stringify(body) }),
  syncRepo: (name: string) =>
    request<{ task: string }>(`/repos/${encodeURIComponent(name)}/sync`, { method: 'POST' }),
  clientConfig: (name: string) =>
    request<string>(`/repos/${encodeURIComponent(name)}/client-config`),
  tasks: (state?: string, limit = 50) =>
    request<Task[]>(`/tasks?limit=${limit}${state ? `&state=${state}` : ''}`),
  task: (id: string) => request<Task>(`/tasks/${id}`),
}
