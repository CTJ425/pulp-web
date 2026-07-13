// 與 BFF schemas.py 對應的型別

export type RepoType = 'rpm' | 'deb' | 'container'

export interface Repo {
  name: string
  type: RepoType
  url: string | null
  policy: string | null
  base_path: string | null
  base_url: string | null
  latest_version: number | null
  last_updated: string | null
  deb_distributions: string | null
  deb_components: string | null
}

export interface RepoCreate {
  name: string
  type: RepoType
  url: string
  policy: 'immediate' | 'on_demand'
  base_path?: string
  deb_distributions?: string
  deb_components?: string
  deb_architectures?: string
  upstream_name?: string
  include_tags?: string[]
}

export type TaskState =
  | 'waiting'
  | 'running'
  | 'completed'
  | 'failed'
  | 'canceled'
  | 'canceling'
  | 'skipped'

export interface Task {
  id: string
  name: string
  state: TaskState | string
  started_at: string | null
  finished_at: string | null
  error: string | null
  progress: string[]
}

export interface Overview {
  repo_counts: Record<RepoType, number>
  running_tasks: number
  failed_tasks: number
  online_workers: number
  online_content_apps: number
  storage_total: number | null
  storage_used: number | null
  storage_free: number | null
  versions: Record<string, string>
}
