import { useState } from 'react'
import { api } from '../api'
import StateBadge from '../components/StateBadge'
import { formatTime, usePolling } from '../hooks'

const FILTERS = ['all', 'running', 'completed', 'failed'] as const

export default function Tasks() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>('all')
  const { data, error } = usePolling(
    () => api.tasks(filter === 'all' ? undefined : filter),
    3_000,
    [filter],
  )

  return (
    <>
      <h1>Tasks</h1>
      <div className="toolbar">
        {FILTERS.map((f) => (
          <button
            key={f}
            className={`chip ${filter === f ? 'chip-active' : ''}`}
            onClick={() => setFilter(f)}
          >
            {f}
          </button>
        ))}
      </div>
      {error && <div className="banner banner-err">無法取得任務:{error}</div>}
      {data && data.length === 0 && <div className="muted">沒有符合的任務。</div>}
      {data && data.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>任務</th>
              <th>狀態</th>
              <th>開始</th>
              <th>結束</th>
              <th>進度 / 錯誤</th>
            </tr>
          </thead>
          <tbody>
            {data.map((t) => (
              <tr key={t.id}>
                <td>
                  <code title={t.id}>{t.name.split('.').pop()}</code>
                </td>
                <td>
                  <StateBadge state={t.state} />
                </td>
                <td>{formatTime(t.started_at)}</td>
                <td>{formatTime(t.finished_at)}</td>
                <td className="progress-cell">
                  {t.error ? (
                    <span className="error-text">{t.error}</span>
                  ) : (
                    t.progress.map((line) => <div key={line}>{line}</div>)
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
