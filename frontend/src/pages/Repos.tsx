import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import ClientConfigModal from '../components/ClientConfigModal'
import RepoForm from '../components/RepoForm'
import StateBadge from '../components/StateBadge'
import { formatTime, usePolling } from '../hooks'
import type { RepoType } from '../types'

const TYPE_FILTERS = ['all', 'rpm', 'deb', 'container'] as const

/** repo 名稱 → 進行中的 task 狀態(sync 或 create 後輪詢) */
type ActiveTasks = Record<string, { taskId: string; state: string }>

export default function Repos() {
  const [filter, setFilter] = useState<(typeof TYPE_FILTERS)[number]>('all')
  const [active, setActive] = useState<ActiveTasks>({})
  const [banner, setBanner] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [configRepo, setConfigRepo] = useState<string | null>(null)

  const { data, error, reload } = usePolling(
    () => api.repos(filter === 'all' ? undefined : (filter as RepoType)),
    10_000,
    [filter],
  )

  // 輪詢進行中的 task;到達終態後移除並刷新列表
  const activeRef = useRef(active)
  activeRef.current = active
  useEffect(() => {
    const pending = Object.keys(active)
    if (pending.length === 0) return
    const timer = setInterval(async () => {
      for (const [name, { taskId }] of Object.entries(activeRef.current)) {
        try {
          const task = await api.task(taskId)
          if (['completed', 'failed', 'canceled'].includes(task.state)) {
            setActive((prev) => {
              const next = { ...prev }
              delete next[name]
              return next
            })
            if (task.state === 'failed') {
              setBanner(`任務失敗(${name}):${task.error ?? '未知錯誤'}`)
            }
            void reload()
          } else {
            setActive((prev) => ({ ...prev, [name]: { taskId, state: task.state } }))
          }
        } catch {
          /* 單次輪詢失敗不中斷;下一輪重試 */
        }
      }
    }, 2_000)
    return () => clearInterval(timer)
  }, [Object.keys(active).join(','), reload]) // eslint-disable-line react-hooks/exhaustive-deps

  const startSync = useCallback(async (name: string) => {
    setBanner(null)
    try {
      const { task } = await api.syncRepo(name)
      setActive((prev) => ({ ...prev, [name]: { taskId: task, state: 'running' } }))
    } catch (e) {
      setBanner(`同步失敗(${name}):${e instanceof ApiError ? e.message : String(e)}`)
    }
  }, [])

  return (
    <>
      <div className="page-head">
        <h1>Repositories</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(true)}>
          + 新增 Repo
        </button>
      </div>
      <div className="toolbar">
        {TYPE_FILTERS.map((f) => (
          <button
            key={f}
            className={`chip ${filter === f ? 'chip-active' : ''}`}
            onClick={() => setFilter(f)}
          >
            {f}
          </button>
        ))}
      </div>
      {banner && (
        <div className="banner banner-err" onClick={() => setBanner(null)}>
          {banner}(點擊關閉)
        </div>
      )}
      {error && <div className="banner banner-err">無法取得 repo 列表:{error}</div>}
      {data && data.length === 0 && <div className="muted">還沒有 repo,點「新增 Repo」建立。</div>}
      {data && data.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>名稱</th>
              <th>型態</th>
              <th>上游</th>
              <th>策略</th>
              <th>版本</th>
              <th>更新時間</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {data.map((repo) => {
              const task = active[repo.name]
              return (
                <tr key={`${repo.type}/${repo.name}`}>
                  <td>
                    <strong>{repo.name}</strong>
                    {repo.base_url && (
                      <div className="muted small">
                        <a href={repo.base_url} target="_blank" rel="noreferrer">
                          {repo.base_url}
                        </a>
                      </div>
                    )}
                  </td>
                  <td>
                    <span className={`type-tag type-${repo.type}`}>{repo.type}</span>
                  </td>
                  <td className="muted">{repo.url ?? '—'}</td>
                  <td>{repo.policy ?? '—'}</td>
                  <td>{repo.latest_version ?? '—'}</td>
                  <td>{formatTime(repo.last_updated)}</td>
                  <td className="actions">
                    {task ? (
                      <StateBadge state={task.state} />
                    ) : (
                      <button className="btn btn-small" onClick={() => void startSync(repo.name)}>
                        Sync now
                      </button>
                    )}
                    <button className="btn btn-small" onClick={() => setConfigRepo(repo.name)}>
                      Client config
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {showForm && (
        <RepoForm
          onClose={() => setShowForm(false)}
          onCreated={(name, task) => {
            setShowForm(false)
            setActive((prev) => ({ ...prev, [name]: { taskId: task, state: 'running' } }))
            void reload()
          }}
        />
      )}
      {configRepo && (
        <ClientConfigModal repoName={configRepo} onClose={() => setConfigRepo(null)} />
      )}
    </>
  )
}
