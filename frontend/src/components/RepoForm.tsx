import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api'
import type { RepoCreate, RepoType } from '../types'

interface Props {
  onCreated: (name: string, task: string) => void
  onClose: () => void
}

export default function RepoForm({ onCreated, onClose }: Props) {
  const [type, setType] = useState<RepoType>('rpm')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    const value = (k: string) => (fd.get(k) as string | null)?.trim() || undefined
    const name = value('name') ?? ''
    const body: RepoCreate = {
      name,
      type,
      url: value('url') ?? '',
      policy: (value('policy') as RepoCreate['policy']) ?? 'on_demand',
      base_path: value('base_path'),
    }
    if (type === 'deb') {
      body.deb_distributions = value('deb_distributions')
      body.deb_components = value('deb_components')
      body.deb_architectures = value('deb_architectures')
    }
    if (type === 'container') {
      body.upstream_name = value('upstream_name')
      const tags = value('include_tags')
      if (tags) body.include_tags = tags.split(',').map((t) => t.trim()).filter(Boolean)
    }
    setSubmitting(true)
    setError(null)
    try {
      const { task } = await api.createRepo(body)
      onCreated(name, task)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>新增 Repository</h2>
        <form onSubmit={submit}>
          <label>
            型態
            <select value={type} onChange={(e) => setType(e.target.value as RepoType)}>
              <option value="rpm">RPM (yum/dnf)</option>
              <option value="deb">DEB (apt)</option>
              <option value="container">Container</option>
            </select>
          </label>
          <label>
            名稱
            <input
              name="name"
              required
              pattern="[a-z0-9][a-z0-9._\-]*"
              title="小寫英數開頭,可含 . _ -"
              placeholder="rocky9-baseos"
            />
          </label>
          <label>
            上游 URL
            <input
              name="url"
              required
              type="url"
              placeholder={
                type === 'container' ? 'https://registry-1.docker.io' : 'https://mirror…/repo/'
              }
            />
          </label>
          <label>
            同步策略
            <select name="policy" defaultValue="on_demand">
              <option value="on_demand">on_demand(用到才抓,建議)</option>
              <option value="immediate">immediate(完整下載)</option>
            </select>
          </label>
          <label>
            Base path(選填,預設同名稱)
            <input name="base_path" placeholder="rocky9/baseos" />
          </label>
          {type === 'deb' && (
            <>
              <label>
                Distributions(suite,空白分隔)
                <input name="deb_distributions" required placeholder="noble" />
              </label>
              <label>
                Components
                <input name="deb_components" placeholder="main" />
              </label>
              <label>
                Architectures
                <input name="deb_architectures" placeholder="amd64" />
              </label>
            </>
          )}
          {type === 'container' && (
            <>
              <label>
                Upstream name
                <input name="upstream_name" required placeholder="library/nginx" />
              </label>
              <label>
                Include tags(逗號分隔,選填)
                <input name="include_tags" placeholder="latest, 1.27" />
              </label>
            </>
          )}
          {error && <div className="banner banner-err">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="btn" onClick={onClose} disabled={submitting}>
              取消
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? '建立中…' : '建立'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
